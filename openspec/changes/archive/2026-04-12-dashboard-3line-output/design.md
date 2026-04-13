## Context

The dashboard (`stokowski/web.py`) renders agent cards with a `.agent-msg` div that displays `r.last_message`. Currently:

1. `RunAttempt.last_message` is truncated to 200 characters by `_process_event()` in `runner.py` (5 truncation sites: lines 321, 625, 632, 636, 773)
2. The Codex runner also truncates at 200 chars (line 321)
3. The Mux runner also truncates at 200 chars (line 773)
4. Dashboard CSS forces 1-line display: `white-space: nowrap; text-overflow: ellipsis; max-width: 620px`

The reviewer clarified: the goal is NOT to show 3 separate messages. The goal is to show more of the last message — enough to fill 3 visual lines (~600 chars at the dashboard's 12px monospace font).

## Goals / Non-Goals

**Goals:**
- Increase `last_message` character limit from 200 to 600 so 3 lines of text are available
- Update dashboard CSS to display up to 3 lines with overflow ellipsis on the 3rd line
- Apply the same limit consistently across all runners (Claude, Codex, Mux)

**Non-Goals:**
- Multiple separate message lines / message history
- Configurable number of lines
- Changing the terminal UI (`main.py`) which uses `[:60]` truncation independently
- Scrollable or expandable output panels

## Decisions

**1. Increase truncation from 200 to 600 characters**
- At 12px IBM Plex Mono with ~620px width, each line holds ~80-90 chars
- 600 chars ≈ 3 lines — matches the request
- This is a simple constant change in `runner.py`

**2. Dashboard CSS: allow 3-line display**
- Remove `white-space: nowrap` from `.agent-msg`
- Remove `max-width: 620px` (the grid column constrains width)
- Use `-webkit-line-clamp: 3` with `display: -webkit-box` and `-webkit-box-orient: vertical` to cap at exactly 3 lines with ellipsis
- Keep `overflow: hidden` for the clamped overflow

**3. Terminal UI (`main.py`) unchanged**
- It independently truncates `last_message[:60]` — this is fine, it's a compact terminal view
- No changes needed in `main.py`

## Risks / Trade-offs

**[Risk] 600-char messages increase API payload slightly**
→ Negligible: 600 vs 200 chars per running agent

**[Risk] Agent cards become taller, reducing how many fit on screen**
→ Acceptable: 3 lines is the explicit request, and the card grid handles variable heights

**[Trade-off] `-webkit-line-clamp` has limited browser support**
→ It works in all modern browsers (Chrome, Firefox, Safari, Edge). The `-webkit-` prefix is widely supported. For full safety, include both `-webkit-line-clamp` and standard `line-clamp`
