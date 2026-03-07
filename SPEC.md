# Stokowski Service Specification

Status: Draft v1 (Claude Code adaptation of [Symphony](https://github.com/openai/symphony))

Purpose: Define a service that orchestrates Claude Code agents to get project work done,
driven by Linear issues.

## 1. Problem Statement

Stokowski is a long-running automation service that continuously reads work from Linear,
creates an isolated workspace for each issue, and runs a Claude Code agent session for
that issue inside the workspace.

The service solves four operational problems:

- Turns issue execution into a repeatable daemon workflow instead of manual scripts.
- Isolates agent execution in per-issue workspaces so agent commands run only inside
  per-issue workspace directories.
- Keeps the workflow policy in-repo (`WORKFLOW.md`) so teams version the agent prompt
  and runtime settings with their code.
- Provides enough observability to operate and debug multiple concurrent agent runs.

### Key difference from Symphony

Symphony uses Codex's app-server JSON-RPC protocol over stdio. Stokowski uses Claude Code's
CLI in headless mode (`claude -p`) with `--output-format stream-json` for structured output
and `--resume` for multi-turn session continuity. This eliminates the need for a custom
protocol implementation - Claude Code handles the agent loop, tool execution, and context
management internally.

Important boundary:

- Stokowski is a scheduler/runner and tracker reader.
- Ticket writes (state transitions, comments, PR links) are performed by the Claude Code
  agent using tools available in the workflow/runtime environment (gh CLI, Linear MCP, etc.).
- A successful run may end at a workflow-defined handoff state (e.g., `Human Review`),
  not necessarily `Done`.

## 2. Goals and Non-Goals

### 2.1 Goals

- Poll Linear on a fixed cadence and dispatch work with bounded concurrency.
- Maintain a single authoritative orchestrator state for dispatch, retries, and reconciliation.
- Create deterministic per-issue workspaces and preserve them across runs.
- Stop active runs when issue state changes make them ineligible.
- Recover from transient failures with exponential backoff.
- Load runtime behavior from a repository-owned `WORKFLOW.md` contract.
- Expose operator-visible observability (structured logs + optional web dashboard).
- Support restart recovery without requiring a persistent database.

### 2.2 Non-Goals

- Rich web UI or multi-tenant control plane.
- General-purpose workflow engine or distributed job scheduler.
- Built-in business logic for how to edit tickets, PRs, or comments.
- API-key-based Claude usage (uses Claude Code subscription via CLI).

## 3. System Overview

### 3.1 Main Components

1. **Workflow Loader**
   - Reads `WORKFLOW.md`.
   - Parses YAML front matter and prompt body.
   - Returns `{config, prompt_template}`.

2. **Config Layer**
   - Exposes typed getters for workflow config values.
   - Applies defaults and environment variable indirection.
   - Performs validation used by the orchestrator before dispatch.

3. **Issue Tracker Client**
   - Fetches candidate issues in active states from Linear.
   - Fetches current states for specific issue IDs (reconciliation).
   - Normalizes tracker payloads into a stable issue model.

4. **Orchestrator**
   - Owns the poll tick.
   - Owns the in-memory runtime state.
   - Decides which issues to dispatch, retry, stop, or release.

5. **Workspace Manager**
   - Maps issue identifiers to workspace paths.
   - Ensures per-issue workspace directories exist.
   - Runs workspace lifecycle hooks.
   - Cleans workspaces for terminal issues.

6. **Agent Runner**
   - Creates workspace.
   - Builds prompt from issue + workflow template.
   - Launches Claude Code via `claude -p` with appropriate flags.
   - Streams agent updates back to the orchestrator.

7. **Status Surface** (optional)
   - Terminal status display or web dashboard.

8. **Logging**
   - Emits structured runtime logs.

### 3.2 Claude Code Integration Model

Unlike Symphony's Codex app-server (a long-running JSON-RPC process), Stokowski integrates
with Claude Code through its CLI interface:

**First turn (new issue):**
```bash
claude -p "<rendered prompt>" \
  --cwd <workspace_path> \
  --dangerously-skip-permissions \
  --output-format stream-json \
  --model <model> \
  --append-system-prompt "<workflow system context>"
```

**Continuation turn (same issue, existing session):**
```bash
claude -p "<continuation guidance>" \
  --cwd <workspace_path> \
  --resume <session_id> \
  --dangerously-skip-permissions \
  --output-format stream-json
```

**Session ID capture:** Extracted from the `stream-json` output or `json` output's
`session_id` field after the first turn.

**Permission model options:**
- `--dangerously-skip-permissions`: Full auto-approve (use in sandboxed environments)
- `--allowedTools "Bash,Read,Edit,Write,Glob,Grep"`: Scoped tool approval

### 3.3 External Dependencies

- Linear API (GraphQL endpoint).
- Local filesystem for workspaces and logs.
- Claude Code CLI (`claude`) installed and authenticated via subscription.
- Git CLI for workspace population.
- Optional: `gh` CLI for GitHub operations.

## 4. Core Domain Model

### 4.1 Entities

#### Issue
Normalized issue record from Linear:
- `id` (string) - Linear internal ID
- `identifier` (string) - Human-readable key (e.g., `COG-123`)
- `title` (string)
- `description` (string or null)
- `priority` (integer or null) - Lower = higher priority
- `state` (string) - Current Linear state name
- `branch_name` (string or null)
- `url` (string or null)
- `labels` (list of strings, lowercase)
- `blocked_by` (list of blocker refs)
- `created_at` (timestamp or null)
- `updated_at` (timestamp or null)

#### Workflow Definition
- `config` (map) - YAML front matter
- `prompt_template` (string) - Markdown body

#### Workspace
- `path` (absolute path)
- `workspace_key` (sanitized issue identifier)
- `created_now` (boolean)

#### Run Attempt
- `issue_id`, `issue_identifier`
- `attempt` (integer or null)
- `workspace_path`
- `started_at`
- `status`
- `session_id` (Claude Code session UUID)
- `error` (optional)

#### Orchestrator Runtime State
- `poll_interval_ms`
- `max_concurrent_agents`
- `running` (map issue_id -> running entry)
- `claimed` (set of issue IDs)
- `retry_attempts` (map issue_id -> retry entry)
- `completed` (set of issue IDs)

## 5. Workflow Specification

### 5.1 File Format

`WORKFLOW.md` is a Markdown file with YAML front matter:

```markdown
---
tracker:
  kind: linear
  project_slug: "my-project-slug"
workspace:
  root: ~/code/workspaces
hooks:
  after_create: |
    git clone --depth 1 git@github.com:org/repo.git .
claude:
  permission_mode: auto
  allowed_tools:
    - Bash
    - Read
    - Edit
    - Write
    - Glob
    - Grep
  model: claude-sonnet-4-6
  max_turns: 20
  turn_timeout_ms: 3600000
  stall_timeout_ms: 300000
agent:
  max_concurrent_agents: 5
---

You are working on Linear ticket `{{ issue.identifier }}`

Issue: {{ issue.title }}
Description: {{ issue.description }}
Status: {{ issue.state }}
Labels: {{ issue.labels }}
URL: {{ issue.url }}

{% if attempt %}
This is continuation attempt #{{ attempt }}.
Resume from workspace state, don't restart from scratch.
{% endif %}

<your workflow instructions here>
```

### 5.2 Front Matter Schema

#### `tracker` (object)
- `kind`: string, required. Currently: `linear`
- `endpoint`: string, default `https://api.linear.app/graphql`
- `api_key`: string or `$VAR`, default reads `$LINEAR_API_KEY`
- `project_slug`: string, required
- `active_states`: list, default `["Todo", "In Progress"]`
- `terminal_states`: list, default `["Closed", "Cancelled", "Canceled", "Duplicate", "Done"]`

#### `polling` (object)
- `interval_ms`: integer, default `30000`

#### `workspace` (object)
- `root`: path, default `<tmpdir>/stokowski_workspaces`

#### `hooks` (object)
- `after_create`: shell script, runs on new workspace creation
- `before_run`: shell script, runs before each agent attempt
- `after_run`: shell script, runs after each agent attempt
- `before_remove`: shell script, runs before workspace deletion
- `timeout_ms`: integer, default `60000`

#### `claude` (object) - replaces Symphony's `codex` section
- `command`: string, default `claude`
- `permission_mode`: one of `auto`, `allowedTools`, default `auto`
  - `auto`: uses `--dangerously-skip-permissions` (sandboxed environments only)
  - `allowedTools`: uses `--allowedTools` with the configured tool list
- `allowed_tools`: list of tool names for `allowedTools` mode
  - Default: `["Bash", "Read", "Edit", "Write", "Glob", "Grep"]`
- `model`: string or null (uses Claude Code default if unset)
- `max_turns`: integer, default `20` - max continuation turns per worker run
- `turn_timeout_ms`: integer, default `3600000` (1 hour)
- `stall_timeout_ms`: integer, default `300000` (5 minutes)
- `append_system_prompt`: string or null - additional system instructions

#### `agent` (object)
- `max_concurrent_agents`: integer, default `5`
- `max_retry_backoff_ms`: integer, default `300000`
- `max_concurrent_agents_by_state`: map state -> integer, default `{}`

### 5.3 Prompt Template

Uses Jinja2-compatible template syntax with these variables:
- `issue` - full normalized issue object
- `attempt` - integer or null (null on first run)

## 6. Orchestration State Machine

### 6.1 Issue States (Internal)
1. **Unclaimed** - Not running, no retry scheduled
2. **Claimed** - Reserved by orchestrator
3. **Running** - Worker process active
4. **RetryQueued** - Retry timer pending
5. **Released** - Claim removed

### 6.2 Run Attempt Lifecycle
1. PreparingWorkspace
2. BuildingPrompt
3. LaunchingAgent
4. StreamingTurn
5. Finishing
6. Succeeded / Failed / TimedOut / Stalled / Canceled

### 6.3 Poll Loop
1. Reconcile running issues
2. Validate config
3. Fetch candidates from Linear
4. Sort by priority
5. Dispatch eligible issues

### 6.4 Retry and Backoff
- Normal continuation: 1000ms fixed delay
- Failure retries: `min(10000 * 2^(attempt-1), max_retry_backoff_ms)`

## 7. Agent Runner Protocol (Claude Code)

### 7.1 Launch

First turn:
```bash
claude -p "<prompt>" \
  --cwd <workspace> \
  --dangerously-skip-permissions \
  --output-format stream-json \
  [--model <model>] \
  [--append-system-prompt "<extra>"]
```

Continuation turns:
```bash
claude -p "<continuation>" \
  --cwd <workspace> \
  --resume <session_id> \
  --dangerously-skip-permissions \
  --output-format stream-json
```

### 7.2 Event Processing

The `stream-json` output emits NDJSON events. Key event types:
- `type: "assistant"` - Agent messages/actions
- `type: "tool_use"` - Tool invocations
- `type: "result"` - Final result with `session_id`, token usage

The runner extracts:
- `session_id` from result events for session continuity
- Token usage from result metadata
- Exit code for success/failure determination

### 7.3 Multi-Turn Processing

After each turn completes:
1. Check if issue is still in an active Linear state
2. If active and turns remaining, start a continuation turn via `--resume`
3. Continuation prompt provides brief guidance, not the full original prompt
4. Same workspace, same session context

### 7.4 Timeout and Stall Detection

- **Turn timeout**: Kill `claude` process after `turn_timeout_ms`
- **Stall detection**: If no stream-json output for `stall_timeout_ms`, kill and retry

## 8. Linear Integration

### 8.1 Required Operations
1. `fetch_candidate_issues()` - Issues in active states for the project
2. `fetch_issues_by_states(states)` - For startup cleanup
3. `fetch_issue_states_by_ids(ids)` - For reconciliation

### 8.2 GraphQL Queries
Standard Linear GraphQL API with:
- Auth via `Authorization: Bearer <LINEAR_API_KEY>`
- Project filtering via `slugId`
- Pagination with cursor-based approach
- Issue normalization per domain model

## 9. Workspace Management

### 9.1 Layout
```
<workspace.root>/
  <sanitized_issue_identifier>/    # e.g., COG-123/
    .git/
    <cloned repo contents>
    CLAUDE.md                       # Optional: per-workspace agent context
```

### 9.2 Safety Invariants
1. Agent runs only in the per-issue workspace path
2. Workspace path must be inside workspace root
3. Workspace key uses only `[A-Za-z0-9._-]`

## 10. Observability

### 10.1 Structured Logging
- Issue context: `issue_id`, `issue_identifier`
- Session context: `session_id`
- Stable `key=value` format

### 10.2 Optional Web Dashboard
- `GET /` - Human-readable dashboard
- `GET /api/v1/state` - JSON runtime state
- `GET /api/v1/<issue_identifier>` - Issue-specific details
- `POST /api/v1/refresh` - Force poll tick

## 11. Trust and Safety

Stokowski runs Claude Code with `--dangerously-skip-permissions` by default.
This is appropriate ONLY in:
- Sandboxed environments (Docker containers, VMs)
- Trusted codebases with CI guardrails
- Development/staging environments

For production use, prefer `--allowedTools` with a scoped tool list.

The agent operates within the per-issue workspace directory. The `--cwd` flag
constrains Claude Code's working directory. Combined with `--allowedTools`,
this provides workspace-scoped execution similar to Symphony's sandbox policies.
