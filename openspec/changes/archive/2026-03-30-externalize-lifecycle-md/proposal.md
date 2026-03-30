## Why

The lifecycle injection section in `prompt.py` contains ~150 lines of hardcoded Python string concatenation for building markdown content (report requirements, gate instructions, rework context, etc.). This mixes content with code logic, making it impossible to customize without modifying source code and creates maintenance burden.

## What Changes

- Extract ALL lifecycle content from `prompt.py` into standalone `.md` files in `prompts/`
- Remove hardcoded strings entirely - `build_lifecycle_section()` becomes a thin wrapper that only loads and renders the external template
- Provide default lifecycle template that operators can copy and customize
- Remove fallback logic - the template file is required (similar to how stage prompts work)

## Capabilities

### New Capabilities
- `lifecycle-template`: Move lifecycle injection content from hardcoded Python to external Jinja2 template files

### Modified Capabilities
- None (refactoring - same behavior, different implementation)

## Impact

- `stokowski/prompt.py`: Remove hardcoded content strings, simplify to pure template loader
- `prompts/lifecycle.md`: New default template file (required)
- `stokowski/config.py`: Make `lifecycle_prompt` required with default path
- All existing deployments: Must add `prompts/lifecycle.md` file (breaking change)
