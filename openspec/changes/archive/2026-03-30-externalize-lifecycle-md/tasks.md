## 1. Extract Content to Template

- [x] 1.1 Create `prompts/lifecycle.md` with all content from current `build_lifecycle_section()`
- [x] 1.2 Convert Python string concatenation to Jinja2 template syntax
- [x] 1.3 Use template conditionals (`{% if %}`) instead of Python `if` statements
- [x] 1.4 Use template loops (`{% for %}`) instead of Python `for` loops

## 2. Simplify Python Code

- [x] 2.1 Remove ALL hardcoded content strings from `build_lifecycle_section()`
- [x] 2.2 Remove `lifecycle_template` parameter - always load from file
- [x] 2.3 Simplify function to: load file → render template → return result
- [x] 2.4 Remove fallback logic and error handling wrappers

## 3. Update Configuration

- [x] 3.1 Make `lifecycle_prompt` required in `PromptsConfig` (no default to None)
- [x] 3.2 Set default value to `"prompts/lifecycle.md"`
- [x] 3.3 Update parsing logic to handle default value

## 4. Create Default Template

- [x] 4.1 Create complete `prompts/lifecycle.md` matching current output format
- [x] 4.2 Include all sections: report requirements, gate info, context, rework, transitions
- [x] 4.3 Add comments documenting available template variables

## 5. Update Integration

- [x] 5.1 Update `assemble_prompt()` to always load lifecycle template
- [x] 5.2 Remove conditional loading logic
- [x] 5.3 Pass full context to `build_lifecycle_section()`

## 6. Documentation

- [x] 6.1 Update README.md to document `lifecycle_prompt` as required
- [x] 6.2 Update workflow.example.yaml with lifecycle_prompt configuration
- [x] 6.3 Document migration path for existing deployments
