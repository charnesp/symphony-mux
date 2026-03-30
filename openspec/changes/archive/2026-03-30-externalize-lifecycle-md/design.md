## Context

The `build_lifecycle_section()` function in `prompt.py` currently contains ~150 lines of hardcoded Python string building:

```python
lines.append("## ⚠️ REQUIRED: Structured Work Report")
lines.append("")
lines.append(
    "**When you complete your work, you MUST include a structured work report..."
)
```

This content should live in external `.md` files like other prompts.

## Goals / Non-Goals

**Goals:**
- Move ALL lifecycle content to external `.md` files
- Simplify `build_lifecycle_section()` to pure template loader/renderer
- No hardcoded content strings in Python

**Non-Goals:**
- Changing the actual content/format of lifecycle output
- Adding new features or capabilities
- Supporting non-Jinja2 template formats

## Decisions

### 1. Required Template File

The lifecycle template becomes **required** (like stage prompts), not optional.

**Rationale**: Consistency with how other prompts work. No hidden fallback means operators can see and customize the content.

### 2. Default Location

Default path: `prompts/lifecycle.md` (can be overridden in config)

**Rationale**: Conventional location alongside other prompt files.

### 3. Build Lifecycle Context

Keep `build_lifecycle_context()` to prepare template variables, but move ALL content to the external template.

### 4. Error Handling

If template file is missing → `FileNotFoundError` with clear message (fail fast)
If template has syntax errors → Jinja2 exception propagates (fail fast)

**Rationale**: Better to fail visibly than silently fall back to hidden defaults.

## Risks / Trade-offs

**Risk**: Breaking change for existing deployments
→ **Mitigation**: Document migration path, provide example template

**Risk**: Template file forgotten in deployment
→ **Mitigation**: Clear error message indicating missing file path

## Migration Plan

1. Create `prompts/lifecycle.md` with content extracted from current code
2. Refactor `build_lifecycle_section()` to load from file
3. Update config to default to `prompts/lifecycle.md`
4. Update documentation
5. Existing users must copy example template to their `prompts/` directory

## Open Questions

- Should we auto-create the template file if missing? (Leaning toward no - explicit is better)
