"""Agent runner - launches Claude Code in headless mode and streams results."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
from collections.abc import Callable
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import ClaudeConfig, HooksConfig
from .models import Issue, RunAttempt
from .workspace import sanitize_key

logger = logging.getLogger("stokowski.runner")

# Callback type for events from the runner to the orchestrator
EventCallback = Callable[[str, str, dict[str, Any]], None]
# Callback for registering/unregistering child PIDs
PidCallback = Callable[[int, bool], None]  # (pid, is_register)

# Report validation marker
REPORT_START_TAG = "<stokowski:report>"
REPORT_END_TAG = "</stokowski:report>"


def _utc_log_timestamp_fragment(at: datetime) -> str:
    """UTC timestamp safe for filenames (no colons)."""
    at = at.replace(tzinfo=UTC) if at.tzinfo is None else at.astimezone(UTC)
    return at.strftime("%Y%m%dT%H%M%S_%f")


def write_claude_agent_output_log(
    log_dir: Path,
    *,
    issue_identifier: str,
    state_name: str | None,
    run_num: int,
    turn_count: int,
    full_output: str,
    at: datetime | None = None,
) -> Path:
    """Write captured Claude stdout (NDJSON lines joined) to a file under ``log_dir``.

    Filenames use sanitized issue id and state, run/turn indices, and a UTC timestamp
    so logs are safe on all platforms and do not overwrite prior captures.
    """
    ts = _utc_log_timestamp_fragment(at or datetime.now(UTC))
    safe_id = sanitize_key(issue_identifier)
    safe_state = sanitize_key(state_name or "unknown")
    name = f"{safe_id}__{safe_state}__run{run_num}_turn{turn_count}__{ts}.log"
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / name
    path.write_text(full_output, encoding="utf-8")
    return path


def _maybe_log_claude_agent_output(log_dir: Path | None, issue: Issue, attempt: RunAttempt) -> None:
    """If ``log_dir`` is set, persist ``attempt.full_output`` and log path + DEBUG preview."""
    if log_dir is None:
        return
    try:
        run_num = int(attempt.attempt or 1)
        path = write_claude_agent_output_log(
            log_dir,
            issue_identifier=issue.identifier,
            state_name=attempt.state_name,
            run_num=run_num,
            turn_count=attempt.turn_count,
            full_output=attempt.full_output or "",
        )
        out_len = len(attempt.full_output or "")
        logger.info(
            "Claude agent output for issue=%s written to %s (%d bytes)",
            issue.identifier,
            path,
            out_len,
        )
        if logger.isEnabledFor(logging.DEBUG):
            preview = (attempt.full_output or "")[:4000]
            logger.debug("Claude agent output preview (first 4000 chars):\n%s", preview)
    except OSError as e:
        logger.warning(
            "Could not write Claude agent output log for issue=%s: %s",
            issue.identifier,
            e,
        )


def validate_agent_output(output_text: str | None) -> tuple[bool, str | None]:
    """Validate that the agent output contains the required stokowski:report.

    Args:
        output_text: The full text output from the agent.

    Returns:
        Tuple of (is_valid, error_message).
        If is_valid is True, error_message is None.
        If is_valid is False, error_message describes what's missing.
    """
    if not output_text:
        return False, "Agent produced no output."

    # Check for opening tag
    if REPORT_START_TAG not in output_text:
        return False, (
            f"MISSING REQUIRED REPORT: Your response must include "
            f"the XML tag `{REPORT_START_TAG}`. "
            f"You MUST wrap your work summary in these tags at the END of your response. "
            f"See the '⚠️ REQUIRED: Structured Work Report' section in the prompt."
        )

    # Check for closing tag
    if REPORT_END_TAG not in output_text:
        return False, (
            f"MISSING CLOSING TAG: Your response has `{REPORT_START_TAG}` but is missing "
            f"the closing tag `{REPORT_END_TAG}`. "
            f"Ensure your report is properly closed."
        )

    # Check tag order
    start_idx = output_text.find(REPORT_START_TAG)
    end_idx = output_text.find(REPORT_END_TAG)
    if start_idx > end_idx:
        return False, (
            f"INVALID TAG ORDER: The closing tag appears before the opening tag. "
            f"Ensure `{REPORT_START_TAG}` comes before `{REPORT_END_TAG}`."
        )

    return True, None


def _finalize_attempt(
    attempt: RunAttempt,
    returncode: int | None,
    stderr_output: str,
    issue_identifier: str,
) -> None:
    """Finalize attempt status based on exit code and report validation.

    This helper encapsulates the common finalization logic for all agent runners.
    It checks the process exit code, validates the report if successful,
    and sets the appropriate status and error message.

    Args:
        attempt: The RunAttempt to finalize (mutated in place).
        returncode: The process exit code.
        stderr_output: Captured stderr output (for error messages).
        issue_identifier: The issue identifier (for logging).
    """
    if attempt.status != "streaming":
        # Already set by stall/timeout handler
        return

    if returncode is None:
        attempt.status = "failed"
        attempt.error = "Process did not return an exit code"
        return

    if returncode == 0:
        # Validate the agent output contains required report
        is_valid, error_msg = validate_agent_output(attempt.full_output)
        if is_valid:
            attempt.status = "succeeded"
        else:
            attempt.status = "failed"
            attempt.error = f"Report validation failed: {error_msg}"
            logger.warning(f"Report validation failed for {issue_identifier}: {error_msg}")
    else:
        attempt.status = "failed"
        attempt.error = f"Exit code {returncode}: {stderr_output}"


def build_claude_args(
    claude_cfg: ClaudeConfig,
    workspace_path: Path,
    session_id: str | None = None,
) -> list[str]:
    """Build the claude CLI argument list.

    Prompt is passed via stdin to avoid argument parsing issues with special chars.
    """
    args = [claude_cfg.command]

    if session_id:
        # Continuation turn
        args.extend(["-p", "", "--resume", session_id])
    else:
        # First turn
        args.extend(["-p", ""])

    args.extend(["--verbose", "--output-format", "stream-json"])

    # Permission mode
    if claude_cfg.permission_mode == "auto":
        args.append("--dangerously-skip-permissions")
    elif claude_cfg.permission_mode == "allowedTools" and claude_cfg.allowed_tools:
        args.extend(["--allowedTools", ",".join(claude_cfg.allowed_tools)])

    # Model override
    if claude_cfg.model:
        args.extend(["--model", claude_cfg.model])

    # System prompt - always include headless context, plus any user additions
    if not session_id:
        headless_context = (
            "You are running in headless/unattended mode via Stokowski orchestrator. "
            "Do NOT use interactive skills, slash commands, or the Skill tool. "
            "Do NOT invoke brainstorming, plan mode, or any interactive workflow. "
            "Work autonomously and directly on the task."
        )
        extra = claude_cfg.append_system_prompt or ""
        combined = f"{headless_context}\n{extra}".strip()
        args.extend(["--append-system-prompt", combined])

    return args


def build_codex_args(
    model: str | None,
    workspace_path: Path,
) -> list[str]:
    """Build the codex CLI argument list.

    Prompt is passed via stdin to avoid argument parsing issues with special chars.
    """
    args = ["codex", "--quiet"]
    if model:
        args.extend(["--model", model])
    args.extend(["--prompt", "-"])  # Read from stdin
    return args


async def run_codex_turn(
    model: str | None,
    hooks_cfg: HooksConfig,
    prompt: str,
    workspace_path: Path,
    issue: Issue,
    attempt: RunAttempt,
    on_pid: PidCallback | None = None,
    turn_timeout_ms: int = 3_600_000,
    stall_timeout_ms: int = 300_000,
    env: dict[str, str] | None = None,
) -> RunAttempt:
    """Run a single Codex turn. Returns updated RunAttempt.

    Codex doesn't support session resumption or stream-json output.
    We capture stdout/stderr and use exit code for status.
    """
    args = build_codex_args(model, workspace_path)

    logger.info(f"Launching codex issue={issue.identifier} turn={attempt.turn_count + 1}")

    # Run before_run hook
    if hooks_cfg.before_run:
        from .workspace import run_hook

        ok = await run_hook(
            hooks_cfg.before_run, workspace_path, hooks_cfg.timeout_ms, "before_run"
        )
        if not ok:
            attempt.status = "failed"
            attempt.error = "before_run hook failed"
            return attempt

    attempt.status = "streaming"
    attempt.started_at = attempt.started_at or datetime.now(UTC)
    attempt.turn_count += 1
    attempt.last_event_at = datetime.now(UTC)

    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            cwd=str(workspace_path),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
            limit=10 * 1024 * 1024,  # 10MB line buffer (default 64KB)
            env=env,
        )

        # Write prompt to stdin (avoids argument parsing issues)
        if proc.stdin:
            proc.stdin.write(prompt.encode())
            await proc.stdin.drain()
            proc.stdin.close()
            await proc.stdin.wait_closed()

        if on_pid and proc.pid:
            on_pid(proc.pid, True)
    except FileNotFoundError:
        attempt.status = "failed"
        attempt.error = "Codex command not found: codex"
        logger.error(attempt.error)
        return attempt

    loop = asyncio.get_running_loop()
    last_activity = loop.time()
    stall_timeout_s = stall_timeout_ms / 1000
    turn_timeout_s = turn_timeout_ms / 1000

    async def read_stream():
        nonlocal last_activity
        output_lines = []
        while proc.stdout:
            line = await proc.stdout.readline()
            if not line:
                break
            last_activity = loop.time()
            attempt.last_event_at = datetime.now(UTC)
            line_str = line.decode().strip()
            if line_str:
                output_lines.append(line_str)
                attempt.last_message = line_str[:200]
        return output_lines

    async def stall_monitor():
        while proc.returncode is None:
            await asyncio.sleep(min(stall_timeout_s / 4, 30))
            elapsed = loop.time() - last_activity
            if stall_timeout_s > 0 and elapsed > stall_timeout_s:
                logger.warning(
                    f"Codex stall detected issue={issue.identifier} elapsed={elapsed:.0f}s"
                )
                proc.kill()
                attempt.status = "stalled"
                attempt.error = f"No output for {elapsed:.0f}s"
                return

    output_lines: list[str] = []
    try:
        reader = asyncio.create_task(read_stream())
        monitor = asyncio.create_task(stall_monitor())

        done, pending = await asyncio.wait(
            {reader, monitor},
            timeout=turn_timeout_s,
            return_when=asyncio.FIRST_COMPLETED,
        )

        if not done:
            logger.warning(f"Codex turn timeout issue={issue.identifier}")
            proc.kill()
            attempt.status = "timed_out"
            attempt.error = f"Turn exceeded {turn_timeout_s}s"
        else:
            await asyncio.wait_for(proc.wait(), timeout=30)
            # Capture output from reader task
            if reader in done:
                try:
                    output_lines = reader.result()
                except Exception:
                    logger.debug("Failed to get reader result", exc_info=True)

        for task in pending:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    except Exception as e:
        logger.error(f"Codex runner error issue={issue.identifier}: {e}")
        proc.kill()
        attempt.status = "failed"
        attempt.error = str(e)
        # Still need to run after_run hook and unregister PID below

    # Store full output for validation and reporting
    attempt.full_output = "\n".join(output_lines)

    # Determine final status from exit code and validate report
    stderr_output = ""
    if proc.stderr:
        try:
            stderr_bytes = await asyncio.wait_for(proc.stderr.read(), timeout=5)
            stderr_output = stderr_bytes.decode()[:500]
        except (TimeoutError, Exception):
            pass
    _finalize_attempt(attempt, proc.returncode, stderr_output, issue.identifier)

    # Run after_run hook
    if hooks_cfg.after_run:
        from .workspace import run_hook

        await run_hook(hooks_cfg.after_run, workspace_path, hooks_cfg.timeout_ms, "after_run")

    # Unregister PID
    if on_pid and proc.pid:
        on_pid(proc.pid, False)

    logger.info(f"Codex turn complete issue={issue.identifier} status={attempt.status}")

    return attempt


async def run_agent_turn(
    claude_cfg: ClaudeConfig,
    hooks_cfg: HooksConfig,
    prompt: str,
    workspace_path: Path,
    issue: Issue,
    attempt: RunAttempt,
    on_event: EventCallback | None = None,
    on_pid: PidCallback | None = None,
    env: dict[str, str] | None = None,
    log_agent_output_dir: Path | None = None,
) -> RunAttempt:
    """Run a single Claude Code turn. Returns updated RunAttempt."""
    args = build_claude_args(claude_cfg, workspace_path, attempt.session_id)

    logger.info(
        f"Launching claude issue={issue.identifier} "
        f"session={attempt.session_id or 'new'} "
        f"turn={attempt.turn_count + 1}"
    )

    # Run before_run hook
    if hooks_cfg.before_run:
        from .workspace import run_hook

        ok = await run_hook(
            hooks_cfg.before_run, workspace_path, hooks_cfg.timeout_ms, "before_run"
        )
        if not ok:
            attempt.status = "failed"
            attempt.error = "before_run hook failed"
            return attempt

    attempt.status = "streaming"
    attempt.started_at = attempt.started_at or datetime.now(UTC)
    attempt.turn_count += 1
    attempt.full_output = ""
    attempt.last_event_at = datetime.now(UTC)

    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            cwd=str(workspace_path),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
            limit=10 * 1024 * 1024,  # 10MB line buffer (default 64KB)
            env=env,
        )

        # Write prompt to stdin (avoids argument parsing issues)
        if proc.stdin:
            proc.stdin.write(prompt.encode())
            await proc.stdin.drain()
            proc.stdin.close()
            await proc.stdin.wait_closed()

        if on_pid and proc.pid:
            on_pid(proc.pid, True)
    except FileNotFoundError:
        attempt.status = "failed"
        attempt.error = f"Claude command not found: {claude_cfg.command}"
        logger.error(attempt.error)
        return attempt

    # Stream stdout (NDJSON events)
    loop = asyncio.get_running_loop()
    last_activity = loop.time()
    stall_timeout_s = claude_cfg.stall_timeout_ms / 1000
    turn_timeout_s = claude_cfg.turn_timeout_ms / 1000

    async def read_stream():
        nonlocal last_activity
        output_lines: list[str] = []
        try:
            while proc.stdout:
                line = await proc.stdout.readline()
                if not line:
                    break
                last_activity = loop.time()
                attempt.last_event_at = datetime.now(UTC)

                line_str = line.decode().strip()
                output_lines.append(line_str)
                if not line_str:
                    continue

                try:
                    event = json.loads(line_str)
                except json.JSONDecodeError:
                    continue

                _process_event(event, attempt, on_event, issue.identifier)
        finally:
            attempt.full_output = "\n".join(output_lines)
            logger.debug(
                "Captured full_output for %s: %d chars",
                issue.identifier,
                len(attempt.full_output),
            )

    async def stall_monitor():
        while proc.returncode is None:
            await asyncio.sleep(min(stall_timeout_s / 4, 30))
            elapsed = loop.time() - last_activity
            if stall_timeout_s > 0 and elapsed > stall_timeout_s:
                logger.warning(f"Stall detected issue={issue.identifier} elapsed={elapsed:.0f}s")
                proc.kill()
                attempt.status = "stalled"
                attempt.error = f"No output for {elapsed:.0f}s"
                return

    reader_task: asyncio.Task[None] | None = None
    monitor_task: asyncio.Task[None] | None = None
    stream_exc: BaseException | None = None
    try:
        reader_task = asyncio.create_task(read_stream())
        monitor_task = asyncio.create_task(stall_monitor())

        # Overall turn timeout
        done, pending = await asyncio.wait(
            {reader_task, monitor_task},
            timeout=turn_timeout_s,
            return_when=asyncio.FIRST_COMPLETED,
        )

        if not done:
            # Turn timeout
            logger.warning(f"Turn timeout issue={issue.identifier}")
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
            attempt.status = "timed_out"
            attempt.error = f"Turn exceeded {turn_timeout_s}s"
        else:
            try:
                await asyncio.wait_for(proc.wait(), timeout=30)
            except TimeoutError:
                logger.warning("Claude subprocess wait timed out issue=%s", issue.identifier)
                with contextlib.suppress(ProcessLookupError):
                    proc.kill()
                if attempt.status == "streaming":
                    attempt.status = "failed"
                    attempt.error = "Claude subprocess did not exit within 30s after stream ended"

        for task in pending:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    except Exception as e:
        stream_exc = e
        logger.error(f"Runner error issue={issue.identifier}: {e}")
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        attempt.status = "failed"
        attempt.error = str(e)
    finally:
        for t in (reader_task, monitor_task):
            if t is not None and not t.done():
                t.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await t

    if stream_exc is not None:
        _maybe_log_claude_agent_output(log_agent_output_dir, issue, attempt)
        return attempt

    # Determine final status from exit code and validate report
    stderr_output = ""
    if proc.stderr:
        try:
            stderr_bytes = await asyncio.wait_for(proc.stderr.read(), timeout=5)
            stderr_output = stderr_bytes.decode()[:500]
        except (TimeoutError, Exception):
            pass
    _maybe_log_claude_agent_output(log_agent_output_dir, issue, attempt)
    _finalize_attempt(attempt, proc.returncode, stderr_output, issue.identifier)

    # Run after_run hook
    if hooks_cfg.after_run:
        from .workspace import run_hook

        await run_hook(hooks_cfg.after_run, workspace_path, hooks_cfg.timeout_ms, "after_run")

    # Unregister PID
    if on_pid and proc.pid:
        on_pid(proc.pid, False)

    logger.info(
        f"Turn complete issue={issue.identifier} "
        f"status={attempt.status} "
        f"tokens={attempt.total_tokens}"
    )

    return attempt


def _process_event(
    event: dict,
    attempt: RunAttempt,
    on_event: EventCallback | None,
    identifier: str,
):
    """Process a single NDJSON event from Claude Code stream-json output."""
    event_type = event.get("type", "")
    attempt.last_event = event_type

    # Extract session_id from result events
    if event_type == "result":
        if "session_id" in event:
            attempt.session_id = event["session_id"]
        # Extract token usage
        usage = event.get("usage", {})
        if usage:
            attempt.input_tokens = usage.get("input_tokens", attempt.input_tokens)
            attempt.output_tokens = usage.get("output_tokens", attempt.output_tokens)
            attempt.total_tokens = (
                usage.get("total_tokens", 0) or attempt.input_tokens + attempt.output_tokens
            )
        # Extract result text for last_message
        result_text = event.get("result", "")
        if isinstance(result_text, str) and result_text:
            attempt.last_message = result_text[:200]

    elif event_type == "assistant":
        # Assistant message content
        msg = event.get("message", {})
        content = msg.get("content", "")
        if isinstance(content, str) and content:
            attempt.last_message = content[:200]
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    attempt.last_message = block.get("text", "")[:200]
                    break

    elif event_type == "tool_use":
        tool_name = event.get("name", event.get("tool", ""))
        attempt.last_message = f"Using tool: {tool_name}"

    # Forward to orchestrator callback
    if on_event:
        on_event(identifier, event_type, event)


def build_mux_args(
    model: str | None,
    workspace_path: Path,
) -> list[str]:
    """Build the mux run CLI argument list.

    Uses --quiet mode for cleaner output.
    Prompt is passed via stdin to avoid argument parsing issues with special chars.
    """
    args = ["npx", "mux", "run", "--quiet", "--json"]

    if model:
        args.extend(["--model", model])

    return args


async def run_mux_turn(
    model: str | None,
    hooks_cfg: HooksConfig,
    prompt: str,
    workspace_path: Path,
    issue: Issue,
    attempt: RunAttempt,
    on_pid: PidCallback | None = None,
    turn_timeout_ms: int = 3_600_000,
    stall_timeout_ms: int = 300_000,
    env: dict[str, str] | None = None,
) -> RunAttempt:
    """Run a single Mux turn. Returns updated RunAttempt.

    Mux uses npx to run without global installation.
    Uses --json for NDJSON streaming output.
    """
    args = build_mux_args(
        model=model,
        workspace_path=workspace_path,
    )

    logger.info(
        f"Launching mux issue={issue.identifier} turn={attempt.turn_count + 1} model={model}"
    )
    logger.info(f"MUX PROMPT for {issue.identifier}:\n{'=' * 60}\n{prompt}\n{'=' * 60}")

    # Run before_run hook
    if hooks_cfg.before_run:
        from .workspace import run_hook

        ok = await run_hook(
            hooks_cfg.before_run, workspace_path, hooks_cfg.timeout_ms, "before_run"
        )
        if not ok:
            attempt.status = "failed"
            attempt.error = "before_run hook failed"
            return attempt

    attempt.status = "streaming"
    attempt.started_at = attempt.started_at or datetime.now(UTC)
    attempt.turn_count += 1
    attempt.last_event_at = datetime.now(UTC)

    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            cwd=str(workspace_path),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
            limit=10 * 1024 * 1024,
            env=env,
        )

        # Write prompt to stdin (avoids argument parsing issues)
        if proc.stdin:
            proc.stdin.write(prompt.encode())
            await proc.stdin.drain()
            proc.stdin.close()
            await proc.stdin.wait_closed()

        if on_pid and proc.pid:
            on_pid(proc.pid, True)
    except FileNotFoundError:
        attempt.status = "failed"
        attempt.error = "npx command not found: ensure Node.js is installed"
        logger.error(attempt.error)
        return attempt

    # Stream stdout (NDJSON events from --json flag)
    loop = asyncio.get_running_loop()
    last_activity = loop.time()
    stall_timeout_s = stall_timeout_ms / 1000
    turn_timeout_s = turn_timeout_ms / 1000

    async def read_stream():
        nonlocal last_activity
        raw_output_lines = []
        assistant_messages = []

        # Debug: optionally save raw NDJSON to file (controlled by env var)
        debug_ndjson = os.environ.get("STOKOWSKI_DEBUG_NDJSON", "")
        with ExitStack() as stack:
            debug_file = None
            if debug_ndjson:
                debug_ndjson_path = (
                    f"/tmp/stokowski_ndjson_{issue.identifier.replace('-', '_')}.json"  # nosec B108
                )
                debug_file = stack.enter_context(open(debug_ndjson_path, "w"))
                logger.info(f"Saving raw NDJSON to {debug_ndjson_path}")

            while proc.stdout:
                line = await proc.stdout.readline()
                if not line:
                    break
                last_activity = loop.time()
                attempt.last_event_at = datetime.now(UTC)

                line_str = line.decode().strip()
                if not line_str:
                    continue

                raw_output_lines.append(line_str)
                if debug_file:
                    debug_file.write(line_str + "\n")
                    debug_file.flush()
                attempt.last_message = line_str[:200]

            # Parse as JSON and extract assistant messages
            try:
                event = json.loads(line_str)
                # Mux JSON format: {"type": "event", "payload": {...}}
                if isinstance(event, dict):
                    event_type = event.get("type", "")

                    # Debug: log event types we see
                    if event_type not in ("event", "caught-up"):
                        logger.debug(f"Mux event type: {event_type}")

                    # Handle Mux format: wrapped in "event" type with payload
                    if event_type == "event":
                        payload = event.get("payload", {})
                        payload_type = payload.get("type", "")

                        # Debug: log payload types (limit frequency)
                        if payload_type not in ("stream-delta", "runtime-status"):
                            logger.debug(
                                f"Mux payload type: {payload_type}, keys: {list(payload.keys())}"
                            )

                        # Stream-end contains the complete message with parts
                        # Take ALL text parts and concatenate them
                        if payload_type == "stream-end":
                            parts = payload.get("parts", [])
                            text_parts = []
                            for part in parts:
                                if part.get("type") == "text":
                                    text = part.get("text", "")
                                    if text:
                                        text_parts.append(text)
                            if text_parts:
                                combined_text = "".join(text_parts)
                                assistant_messages.append(combined_text)
                                logger.info(
                                    f"Mux: Extracted {len(combined_text)} chars from {len(text_parts)} text parts"
                                )

                        # Token usage from run-complete
                    elif event_type == "run-complete":
                        usage = event.get("usage", {})
                        if usage:
                            attempt.input_tokens = usage.get("inputTokens", 0)
                            attempt.output_tokens = usage.get("outputTokens", 0)
                            attempt.total_tokens = usage.get("inputTokens", 0) + usage.get(
                                "outputTokens", 0
                            )

                    # Handle Claude Code format (for compatibility)
                    elif event_type == "assistant":
                        msg = event.get("message", {})
                        content = msg.get("content", "")
                        if content:
                            assistant_messages.append(content)
                    elif event_type == "result":
                        # Extract token usage from result
                        usage = event.get("usage", {})
                        if usage:
                            attempt.input_tokens = usage.get("input_tokens", 0)
                            attempt.output_tokens = usage.get("output_tokens", 0)
                            attempt.total_tokens = (
                                usage.get("total_tokens", 0)
                                or attempt.input_tokens + attempt.output_tokens
                            )
                        # Also check for direct result text
                        result_text = event.get("result", "")
                        if isinstance(result_text, str) and result_text:
                            assistant_messages.append(result_text)
            except json.JSONDecodeError:
                # Not JSON - Mux may output plain text alongside NDJSON
                # Collect these lines as assistant output
                if line_str.strip():
                    assistant_messages.append(line_str)
                    logger.debug(f"Mux: Non-JSON text ({len(line_str)} chars)")

            # Store raw NDJSON for debugging, but also reconstructed readable output
            readable_output = "\n".join(assistant_messages)
            attempt.full_output = readable_output

        logger.info(
            f"MUX OUTPUT for {issue.identifier}:\n{'=' * 60}\n{readable_output}\n{'=' * 60}"
        )
        if debug_ndjson:
            logger.info(f"Raw NDJSON saved to {debug_ndjson_path} ({len(raw_output_lines)} lines)")
        return raw_output_lines

    async def stall_monitor():
        while proc.returncode is None:
            await asyncio.sleep(min(stall_timeout_s / 4, 30))
            elapsed = loop.time() - last_activity
            if stall_timeout_s > 0 and elapsed > stall_timeout_s:
                logger.warning(
                    f"Mux stall detected issue={issue.identifier} elapsed={elapsed:.0f}s"
                )
                proc.kill()
                attempt.status = "stalled"
                attempt.error = f"No output for {elapsed:.0f}s"
                return

    try:
        reader = asyncio.create_task(read_stream())
        monitor = asyncio.create_task(stall_monitor())

        done, pending = await asyncio.wait(
            {reader, monitor},
            timeout=turn_timeout_s,
            return_when=asyncio.FIRST_COMPLETED,
        )

        if not done:
            logger.warning(f"Mux turn timeout issue={issue.identifier}")
            proc.kill()
            attempt.status = "timed_out"
            attempt.error = f"Turn exceeded {turn_timeout_s}s"
        else:
            await asyncio.wait_for(proc.wait(), timeout=30)

        for task in pending:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    except Exception as e:
        logger.error(f"Mux runner error issue={issue.identifier}: {e}")
        proc.kill()
        attempt.status = "failed"
        attempt.error = str(e)

    # Determine final status from exit code and validate report
    stderr_output = ""
    if proc.stderr:
        try:
            stderr_bytes = await asyncio.wait_for(proc.stderr.read(), timeout=5)
            stderr_output = stderr_bytes.decode()[:500]
        except (TimeoutError, Exception):
            pass
    _finalize_attempt(attempt, proc.returncode, stderr_output, issue.identifier)

    # Run after_run hook
    if hooks_cfg.after_run:
        from .workspace import run_hook

        await run_hook(hooks_cfg.after_run, workspace_path, hooks_cfg.timeout_ms, "after_run")

    # Unregister PID
    if on_pid and proc.pid:
        on_pid(proc.pid, False)

    logger.info(f"Mux turn complete issue={issue.identifier} status={attempt.status}")

    return attempt


async def run_turn(
    runner_type: str,
    claude_cfg: ClaudeConfig,
    hooks_cfg: HooksConfig,
    prompt: str,
    workspace_path: Path,
    issue: Issue,
    attempt: RunAttempt,
    on_event: EventCallback | None = None,
    on_pid: PidCallback | None = None,
    env: dict[str, str] | None = None,
    log_agent_output_dir: Path | None = None,
) -> RunAttempt:
    """Route to the correct runner based on runner_type."""
    if runner_type == "codex":
        return await run_codex_turn(
            model=claude_cfg.model,
            hooks_cfg=hooks_cfg,
            prompt=prompt,
            workspace_path=workspace_path,
            issue=issue,
            attempt=attempt,
            on_pid=on_pid,
            turn_timeout_ms=claude_cfg.turn_timeout_ms,
            stall_timeout_ms=claude_cfg.stall_timeout_ms,
            env=env,
        )
    elif runner_type == "mux":
        return await run_mux_turn(
            model=claude_cfg.model,
            hooks_cfg=hooks_cfg,
            prompt=prompt,
            workspace_path=workspace_path,
            issue=issue,
            attempt=attempt,
            on_pid=on_pid,
            turn_timeout_ms=claude_cfg.turn_timeout_ms,
            stall_timeout_ms=claude_cfg.stall_timeout_ms,
            env=env,
        )
    elif runner_type == "claude":
        return await run_agent_turn(
            claude_cfg=claude_cfg,
            hooks_cfg=hooks_cfg,
            prompt=prompt,
            workspace_path=workspace_path,
            issue=issue,
            attempt=attempt,
            on_event=on_event,
            on_pid=on_pid,
            env=env,
            log_agent_output_dir=log_agent_output_dir,
        )
    else:
        raise ValueError(f"Unknown runner type: {runner_type}")
