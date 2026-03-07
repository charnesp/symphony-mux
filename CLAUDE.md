# Stokowski

Claude Code adaptation of OpenAI's Symphony. Orchestrates Claude Code agents via Linear issues.

## Architecture

- `stokowski/` - Python package (asyncio-based orchestrator)
  - `config.py` - WORKFLOW.md parser, typed config with defaults
  - `linear.py` - Linear GraphQL client (httpx async)
  - `models.py` - Domain models (Issue, RunAttempt, RetryEntry)
  - `orchestrator.py` - Main poll loop, dispatch, reconciliation, retry logic
  - `runner.py` - Claude Code CLI integration (claude -p + stream-json)
  - `workspace.py` - Per-issue workspace lifecycle and hooks
  - `web.py` - Optional FastAPI dashboard
  - `main.py` - CLI entry point
- `SPEC.md` - Full specification (adapted from Symphony's SPEC.md)
- `WORKFLOW.md` - Example workflow config + prompt template

## Key design decisions

- Uses `claude -p --output-format stream-json` instead of Codex app-server JSON-RPC
- Session continuity via `--resume <session_id>` (captured from stream-json output)
- Permission control via `--dangerously-skip-permissions` or `--allowedTools`
- Python + asyncio for simplicity (vs Symphony's Elixir/OTP)
- No API keys needed - uses Claude Code subscription auth

## Development

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[web]"
stokowski --dry-run  # validate config
stokowski -v         # run with verbose logging
```

## Testing

Run with `--dry-run` to validate config and preview Linear candidates without dispatching agents.
