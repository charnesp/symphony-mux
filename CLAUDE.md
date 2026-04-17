# Stokowski

Claude Code adaptation of [OpenAI's Symphony](https://github.com/openai/symphony). Orchestrates Claude Code agents via Linear issues.

This file is the single source of truth for contributors. It covers architecture, design decisions, key behaviours, and how to work on the codebase.

---

## What it does

Stokowski is a long-running Python daemon that:
1. Polls Linear for issues in configured active states
2. Creates an isolated git-cloned workspace per issue
3. Launches Claude Code (`claude -p`) in that workspace
4. Manages multi-turn sessions via `--resume <session_id>`
5. Retries failures with exponential backoff
6. Reconciles running agents against Linear state changes
7. Exposes a live web dashboard and terminal UI

The agent prompt, runtime config, and workspace setup all live in `workflow.yaml` in the operator's directory — not in this codebase.

---

## Package structure

```
stokowski/
  agent_gate_route.py  Parse <<<STOKOWSKI_ROUTE>>> JSON + format routing-error comments
  config.py        workflow.yaml parser + typed config dataclasses
  datetime_parse.py Shared UTC normalization for Linear ISO timestamps (used by linear + tracking)
  linear.py        Linear GraphQL client (httpx async)
  models.py        Domain models: Issue, RunAttempt, RetryEntry
  orchestrator.py  Main poll loop, dispatch, reconciliation, retry
  prompt.py        Three-layer prompt assembly for state machine workflows
  runner.py        Claude Code CLI integration, stream-json parser
  tracking.py      State machine tracking via structured Linear comments
  workspace.py     Per-issue workspace lifecycle and hooks
  web.py           Optional FastAPI dashboard
  main.py          CLI entry point, keyboard handler
  __main__.py      Enables python -m stokowski
```

---

## Key design decisions

### Claude Code CLI instead of Codex app-server
Symphony uses Codex's JSON-RPC `app-server` protocol over stdio. Stokowski uses Claude Code's CLI:
- First turn: `claude -p "<prompt>" --output-format stream-json --verbose`
- Continuation: `claude -p "<prompt>" --resume <session_id> --output-format stream-json --verbose`

`--verbose` is required for `stream-json` to work. `session_id` is extracted from the `result` event in the NDJSON stream.

### Python + asyncio instead of Elixir/OTP
Simpler operational story — single process, no BEAM runtime, no distributed concerns. Concurrency via `asyncio.create_task`. Each agent turn is a subprocess launched with `asyncio.create_subprocess_exec`.

### No persistent database
All state lives in memory. The orchestrator recovers from restart by re-polling Linear and re-discovering active issues. Workspace directories on disk act as durable state.

### workflow.yaml as the operator contract
The operator's `workflow.yaml` defines the runtime config and state machine. Stokowski re-parses it on every poll tick — config changes take effect without restart. Both `.yaml` and legacy `.md` (YAML front matter + Jinja2 body) formats are supported. Prompt templates are now separate `.md` files referenced by path from the config.

### State machine workflow
Each workflow defines a set of internal states that map to Linear states. States have types: `agent` (runs the configured runner), `agent-gate` (same runner stack, then a machine-chosen transition from structured stdout), `gate` (waits for human review), or `terminal` (issue complete). Transitions between states are declared explicitly in config.

**Agent-gate:** Same runner stack and `prompt:` as `agent`. YAML requires explicit **`post_run`** (`true` or `false`). Typical routing gates use **`post_run: false`** (one turn; report + `<<<STOKOWSKI_ROUTE>>>` live in the stage prompt). YAML also requires `transitions` (named keys → target states), plus `default_transition` naming one of those keys whose **target** must be `type: gate` (human validation when routing fails). After success, Stokowski parses routing from the **canonical** runner output (the post-run turn when `post_run: true`, otherwise the single work turn), calls `_safe_transition` with the chosen key, and posts `<stokowski:report>` from that same output. If parsing fails, it posts a `route-error` comment and uses `default_transition`. See `.stokowski/prompts/lifecycle-post-run.md`, `.stokowski/prompts/lifecycle.md`, and `workflow.example.yaml`.

**Three-layer prompt assembly (work turn):** Prompt composition is session-aware. Fresh **work** turns include all three layers; resumed turns always include **pre-run** lifecycle and may include stage only when entering a new stage in the resumed session (post-run is only used after a successful work turn when `effective_post_run` is true — it is **not** part of resumed-session static prompt skipping; the follow-up is always the dedicated post-run template):
1. **Global prompt** — shared context loaded from a `.md` file (referenced by `prompts.global_prompt`)
2. **Stage prompt** — state-specific instructions loaded from the state's `prompt` path
3. **Pre-run lifecycle** — `prompts.lifecycle_prompt`: issue metadata, transitions, rework context, recent comments (`lifecycle_phase` = `pre`)

**Gate protocol:** When an agent completes a state that transitions to a gate, Stokowski moves the issue to the gate's Linear state and posts a structured tracking comment. Humans approve or request rework via Linear state changes. On approval, Stokowski advances to the gate's `approve` transition target. On rework, it returns to the gate's `rework_to` state.

**Structured comment tracking:** State transitions and gate decisions are persisted as HTML comments on Linear issues (`<!-- stokowski:state {...} -->` and `<!-- stokowski:gate {...} -->`). These enable crash recovery and provide context for rework runs.

### Workspace isolation
Each issue gets its own directory under `workspace.root`. Agents run with `cwd` set to that directory. Workspaces persist across turns for the same session; they're deleted when the issue reaches a terminal state.

### Headless system prompt
Every first-turn launch appends a system prompt via `--append-system-prompt` that instructs Claude not to use interactive skills, slash commands, or plan mode. This prevents agents from stalling on interactive workflows.

### Multi-workflow support
Stokowski supports multiple workflows via the `workflows:` section in `workflow.yaml`. Each workflow is triggered by a Linear label on the issue:

```yaml
workflows:
  debug:
    label: debug
    states: { ... }
    prompts:
      global_prompt: prompts/debug/global.md

  feature:
    label: feature
    default: true  # Fallback for issues without matching labels
    states: { ... }
```

**Routing rules:**
- Issues are routed to workflows based on their Linear labels (exact match)
- First match wins (YAML order) if multiple labels match
- One workflow can be marked `default: true` as fallback
- If no workflow matches and no default exists, dispatch fails with clear error

**Backwards compatibility:** If `workflows:` is absent, Stokowski creates an implicit "default" workflow from the root `states:` and `prompts:` sections. Existing single-workflow configs continue working without changes.

---

## Component deep-dives

### config.py
Parses `workflow.yaml` (or legacy `.md` with front matter) into typed dataclasses:
- `TrackerConfig` — Linear endpoint, API key, project slug
- `PollingConfig` — interval
- `WorkspaceConfig` — root path (supports `~` and `$VAR` expansion)
- `HooksConfig` — shell scripts for lifecycle events + timeout (includes `on_stage_enter`)
- `ClaudeConfig` — command, permission mode, model, timeouts, system prompt
- `AgentConfig` — concurrency limits (global + per-state)
- `ServerConfig` — optional web dashboard port
- `LinearStatesConfig` — maps logical state names (`todo`, `active`, `review`, `gate_approved`, `rework`, `terminal`) to actual Linear state names. Issues in the `todo` state are picked up and automatically moved to `active` on dispatch.
- `PromptsConfig` — global prompt file reference
- `StateConfig` — a single state in the state machine: type, prompt path, linear_state key, runner, session mode, transitions, optional `default_transition` for `agent-gate`, per-state overrides (model, max_turns, timeouts, hooks), gate-specific fields (rework_to, max_rework; forbidden on `agent-gate`)
- `WorkflowConfig` — a complete workflow with label trigger, default flag, states dict, and prompts config

`ServiceConfig` provides helper methods: `entry_state` (first `agent` or `agent-gate` state), `active_linear_states()`, `gate_linear_states()`, `terminal_linear_states()`, `get_workflow_for_issue(issue)` (routes by label), `entry_state_for_workflow(workflow)`.

`merge_state_config(state, root_claude, root_hooks)` merges per-state overrides with root defaults — only specified fields are overridden. Returns `(ClaudeConfig, HooksConfig)`.

`parse_workflow_file()` detects format by file extension: `.yaml`/`.yml` files are parsed as pure YAML; `.md` files are split on `---` delimiters for front matter + body.

`validate_config()` checks state machine integrity: all transitions point to existing states, gates have `rework_to` and `approve` transition, at least one `agent` or `agent-gate` state and one terminal state exist, `agent-gate` constraints (`default_transition`, fallback target is a gate, no `rework_to`/`max_rework`), warns about unreachable states.

`ServiceConfig.resolved_api_key()` resolves the key in priority order:
1. Literal value in YAML
2. `$VAR` reference resolved from env
3. `LINEAR_API_KEY` env var as fallback

`ServiceConfig.resolved_project_slug()` follows the same three-tier pattern:
1. Literal value in YAML
2. `$VAR` reference resolved from env
3. `LINEAR_PROJECT_SLUG` env var as fallback

### linear.py
Async GraphQL client over httpx. Core queries:
- `fetch_candidate_issues()` — paginated, fetches all issues in active states with full detail (labels, blockers, branch name)
- `fetch_issue_states_by_ids()` — lightweight reconciliation query, returns `{id: state_name}`
- `fetch_issues_by_states()` — used on startup cleanup, returns minimal Issue objects
- `fetch_comments()` — returns `CommentsFetchResult(nodes, complete)`. Paginates (`first` + `after`) until `hasNextPage` is false or a safety page cap is hit; dedupes by comment `id`; logs and returns `complete=False` if `hasNextPage` without `endCursor`, the cap is exceeded, or `nodes` is not a list. Raises `LinearCommentsFetchError` if the **first** GraphQL page fails (so callers do not treat that as an empty thread). After at least one successful page, errors return partial `nodes` with `complete=False`.

Note: the reconciliation query uses `issues(filter: { id: { in: $ids } })` — not `nodes(ids:)` which doesn't exist in Linear's API.

**Image Attachments:** `COMMENTS_QUERY` includes attachment data. The `download_comment_images()` method filters for `sourceType == "image"` attachments, downloads them to the workspace `images/` directory using the Linear API key for authentication, and validates downloaded files by magic bytes (PNG, JPEG, GIF, WebP, HEIC). Images are cached (skipped if already exist) and size-limited. Returns comments with `downloaded_images` key containing local paths and metadata.

### models.py
Three dataclasses:
- `Issue` — normalized Linear issue. `title` is required even for minimal fetches (use `title=""`).
- `RunAttempt` — per-issue runtime state: session_id, turn count, token usage, status, last message
- `RetryEntry` — retry queue entry with due time and error

### orchestrator.py
The main loop. `start()` runs until `stop()` is called:

```
while running:
    _tick()          # reconcile → fetch → dispatch
    sleep(interval)  # interruptible via asyncio.Event
```

**Dispatch logic:**
1. Issues sorted by priority (lower = higher), then created_at, then identifier
2. `_is_eligible()` checks: valid fields, active state, not already running/claimed, blockers resolved
3. Per-state concurrency limits checked against `max_concurrent_agents_by_state`
4. `_dispatch()` creates a `RunAttempt`, adds to `self.running`, spawns `_run_worker` task

**Reconciliation:** on each tick, fetches current states for all running issue IDs. If an issue moved to terminal state → cancel worker + clean workspace. If moved out of active states → cancel worker, release claim.

**Retry logic:**
- `succeeded` → normally `_safe_transition` / further dispatch as implemented in `_on_worker_exit`; a **1s continuation retry** applies only to the legacy escape hatch when success occurs but `attempt.state_name` is missing from the workflow states used for that check
- `failed/timed_out/stalled` → exponential backoff: `min(10000 * 2^(attempt-1), max_retry_backoff_ms)`
- `canceled` → release claim immediately

**Shutdown:** `stop()` sets `_stop_event`, kills all child PIDs via `os.killpg`, cancels async tasks.

### runner.py
`run_agent_turn()` builds CLI args, launches subprocess, streams NDJSON output.

**PID tracking:** `on_pid` callback registers/unregisters child PIDs with the orchestrator for clean shutdown.

**Stall detection:** background `stall_monitor()` task checks time since last output. Kills process if `stall_timeout_ms` exceeded.

**Turn timeout:** `asyncio.wait()` with `turn_timeout_ms` as overall deadline.

**Event processing** (`_process_event`):
- `result` event → extracts `session_id`, token usage, result text
- `assistant` event → extracts last message for display
- `tool_use` event → updates last message with tool name

### workspace.py
`ensure_workspace()` creates the directory if needed, runs `after_create` hook on first creation.
`remove_workspace()` runs `before_remove` hook, then deletes the directory.
`run_hook()` executes shell scripts via `asyncio.create_subprocess_shell` with timeout.

Workspace key is the sanitized issue identifier: only `[A-Za-z0-9._-]` characters.

### web.py
Optional FastAPI app returned by `create_app(orch)`. Routes:
- `GET /` — HTML dashboard (IBM Plex Mono font, dark theme, amber accents)
- `GET /api/v1/state` — full JSON snapshot from `orch.get_state_snapshot()`
- `GET /api/v1/{issue_identifier}` — single issue state
- `POST /api/v1/refresh` — triggers `orch._tick()` immediately

Dashboard JS polls `/api/v1/state` every 3s and updates the DOM without page reload.

Uvicorn is started as an `asyncio.create_task` with `install_signal_handlers` monkey-patched to a no-op to prevent it hijacking SIGINT/SIGTERM. On shutdown, `server.should_exit = True` is set and the task is awaited with a 2s timeout.

### main.py
CLI entry point (`cli()`) and keyboard handler.

**`KeyboardHandler`** runs in a daemon background thread using `tty.setcbreak()` (not `setraw` — `setraw` disables `OPOST` output processing which causes diagonal log output). Uses `select.select()` with 100ms timeout for non-blocking key reads. Restores terminal state in `finally`.

**`_make_footer()`** builds the Rich `Text` status line shown at bottom of terminal via `Live`.

**`check_for_updates()`** hits the GitHub releases API (`/repos/Sugar-Coffee/stokowski/releases/latest`) via httpx, compares the latest tag against the installed `__version__`, and sets `_update_message` if a newer version exists. Best-effort — all exceptions are silently swallowed.

**`_force_kill_children()`** uses `pgrep -f "claude.*-p.*--output-format.*stream-json"` as a last-resort cleanup on `KeyboardInterrupt`.

**`_load_dotenv()`** reads `.env` from cwd on startup — supports `KEY=value` format, ignores comments and blank lines. The project-local `.env` takes precedence over the shell environment (uses direct assignment, overrides existing env vars).

### prompt.py
Three-layer prompt assembly for state machine workflows. Main entry point is `assemble_prompt()`.

**`load_prompt_file(path, workflow_dir)`** resolves a prompt file path (absolute or relative to workflow dir) and returns its contents.

**`render_template(template_str, context)`** renders a Jinja2 template with `_SilentUndefined` — missing variables render as empty strings instead of raising errors.

**`build_template_context(issue, state_name, run, attempt, last_run_at, is_rework)`** builds the dict used for global/stage Jinja2 rendering: `issue` (the `Issue` model), `state_name`, `run`, `attempt`, `last_run_at`, `is_rework`.

**`build_lifecycle_section()`** renders a lifecycle markdown template with Jinja2 (`lifecycle_phase` `pre` or `post`, plus issue / transitions / comments context, and `workflow_name` from the YAML workflow key for conditionals). Used for Layer 3 of `assemble_prompt()` (pre-run) and for `assemble_post_run_lifecycle_prompt()` (post-run only; `embed_images=False` so comment images are not attached on the closure turn).

**`assemble_prompt()`** applies session-aware composition rules for the **work** prompt: global / stage / pre-run lifecycle on fresh turns; pre-run lifecycle only on resumed same-stage turns; stage + pre-run lifecycle on resumed new-stage turns (global stays omitted on resume).

**`assemble_post_run_lifecycle_prompt()`** loads `lifecycle_post_run_prompt` or the default `prompts/lifecycle-post-run.md` and renders it with `lifecycle_phase="post"` — no global or stage layers.

**Image Support:** On the **work** turn, when comments include `downloaded_images`, `build_lifecycle_section()` may append image references via `embed_images_in_prompt()`. The Jinja2 context includes `has_images` and `image_references`. The **post-run** follow-up does not re-embed comment images.

### tracking.py
State machine tracking via structured Linear comments:
- `make_state_comment(state, run)` — builds state entry comment with hidden JSON (`<!-- stokowski:state {...} -->`) + human-readable text
- `make_gate_comment(state, status, prompt, rework_to, run)` — builds gate status comment (waiting/approved/rework/escalated)
- `parse_latest_tracking(comments)` — picks the latest state or gate marker by **effective time** (UTC): `max(JSON timestamp, comment createdAt)` when both parse; otherwise whichever parses; **last** marker wins on ties; multiple markers in one comment are ordered by position in the body. JSON is extracted with **brace-balanced** parsing (not a naive regex) so `}` / `} -->` inside string values does not truncate the payload. Independent of API comment order.
- `parse_latest_gate_waiting(comments)` — same time rules on gate markers with `status: waiting` (used for rework / gate recovery when `_pending_gates` is cold)
- `get_last_tracking_timestamp(comments)` — ISO string for the same winning marker as `parse_latest_tracking` (payload `timestamp` if present, else `createdAt`)
- `get_comments_since(comments, since_timestamp)` — filters to non-tracking comments after a given timestamp (used to gather review feedback for rework runs); parses boundaries with the same UTC-normalization rules as tracking; non-parseable non-empty `since_timestamp` yields **no** human comments (strict); tracking detection uses case-insensitive `<!-- stokowski:` check

---

## Data flow: issue dispatch to PR

```
workflow.yaml parsed → states + config loaded
    → Linear poll → Issue fetched → state resolved from tracking comments
    → _dispatch() called
        → RunAttempt created in self.running
        → _run_worker() task spawned
            → ensure_workspace() → after_create hook (git clone, npm install, etc.)
            → assemble_prompt() → session-aware layering for work turn (fresh: global+stage+pre lifecycle; resumed same-stage: pre lifecycle only; resumed new-stage: stage+pre lifecycle)
            → run_turn() for work; on success, optional second run_turn() with post-run lifecycle only when state.post_run requests it
                → build_claude_args() → claude -p subprocess
                → NDJSON streamed: tool_use events, assistant messages, result
                → session_id captured for next turn
            → _on_worker_exit() called
                → state transition on success → tracking comment posted
                → tokens/timing aggregated
                → retry or continuation scheduled
```

The agent itself handles: moving Linear state, posting comments, creating branches, opening PRs via `gh pr create`, linking PR to issue. Stokowski doesn't do any of that — it's the scheduler, not the agent.

---

## Stream-json event format

Claude Code emits NDJSON on stdout when run with `--output-format stream-json --verbose`. Key event types:

```json
{"type": "assistant", "message": {"content": [{"type": "text", "text": "..."}]}}
{"type": "tool_use", "name": "Bash", "input": {"command": "..."}}
{"type": "result", "session_id": "uuid", "usage": {"input_tokens": 1234, "output_tokens": 456, "total_tokens": 1690}, "result": "final message text"}
```

Exit code 0 = success. Non-zero = failure (stderr captured for error message).

---

## Development setup

This project uses [uv](https://docs.astral.sh/uv/) for dependency management and virtual environments.

```bash
# Install dependencies (creates .venv automatically)
uv sync

# Install with web dashboard dependencies
uv sync --extra web

# Install with test dependencies
uv sync --extra test

# Install pre-commit hooks (recommended)
uv run pre-commit install

# Run tests
uv run pytest tests/ -v

# Validate config without dispatching agents
uv run stokowski --dry-run

# Run with verbose logging
uv run stokowski -v

# Run with web dashboard
uv run stokowski --port 4200
```

### Using uv tool install

For a global installation without cloning:

```bash
# Install from git
uv tool install git+https://github.com/Sugar-Coffee/stokowski.git

# Or install from local clone
cd stokowski
uv tool install .

# Then run directly
stokowski --help
```

### Pre-commit Hooks

The project includes pre-commit hooks for code quality:

- **Tests** (`pytest`) - Must pass before each commit
- **Bandit** - Security vulnerability scanning
- **pip-audit** - Dependency vulnerability checking
- **Ruff** - Linting and code formatting (replaces flake8, black, isort)
- **Pyright** - Type checking
- **YAML/TOML/JSON validation** - Syntax checking

To run hooks manually: `uv run pre-commit run --all-files`

Pre-commit and commit-message gate policy is defined in `AGENTS.md` under `Validation Before Committing` (single source of truth).

---

## Git Workflow

**NEVER push directly to `main`.** All changes must go through a branch and pull request.

### Branch Naming
- Use descriptive branch names: `feature/description`, `fix/description`, `refactor/description`
- Example: `feature/add-mux-runner`, `fix/report-validation`

### Workflow
1. Create a branch from `main`: `git checkout -b feature/my-change`
2. Make commits with clear messages
3. Push the branch: `git push -u origin feature/my-change`
4. Open a Pull Request for review
5. Merge via PR after approval

This ensures code review and prevents accidental breaking changes to production.

---

## Contributing

### Adding a new tracker (not Linear)
1. Add a client in a new file (e.g., `github_issues.py`) implementing the same three methods as `LinearClient`
2. Add the new tracker kind to `config.py` parsing
3. Update `orchestrator.py` to instantiate the right client based on `cfg.tracker.kind`
4. Update `validate_config()` to handle the new kind

### Adding config fields
1. Add the field to the relevant dataclass in `config.py`
2. Parse it in `parse_workflow_file()`
3. Use it wherever needed
4. Update `WORKFLOW.example.md` and the README config reference

### Changing the web dashboard
`web.py` is self-contained. The HTML/CSS/JS is inline in the `HTML` constant. The dashboard is intentionally dependency-free on the frontend — no build step, no npm.

### Common pitfalls
- **`tty.setraw` vs `tty.setcbreak`**: Don't switch back to `setraw`. It disables `OPOST` output processing and causes Rich log lines to render diagonally (no carriage return on newlines).
- **`Issue(title=...)` is required**: Minimal Issue constructors (in `linear.py` `fetch_issues_by_states` and the `orchestrator.py` state-check default) must pass `title=""` — it's a required positional field.
- **`--verbose` with stream-json**: Claude Code requires `--verbose` when using `--output-format stream-json`. Without it you get an error.
- **Linear project slug**: The `project_slug` is the hex `slugId` from the project URL, not the human-readable name. These look like `abc123def456`.
- **Uvicorn signal handlers**: Must be monkey-patched (`server.install_signal_handlers = lambda: None`) before calling `serve()`, otherwise uvicorn hijacks SIGINT.
- **workflow.yaml is pure YAML**: No markdown front matter. The legacy `.md` format with `---` delimiters is still supported but `.yaml` is the canonical format.
- **Prompt files use Jinja2 with silent undefined**: Missing variables become empty strings rather than raising errors. This is intentional — not all variables are available in every context.
