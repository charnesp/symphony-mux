## Context

Currently, Stokowski uses HTML-style comment markers for machine-readable tracking data in Linear comments:

**Current format (at BEGINNING of comment):**
```
<!-- stokowski:state {"state": "investigate", "run": 1, "timestamp": "2026-04-13T10:18:49.189659+00:00", "workflow": "feature"} -->

**[Stokowski]** Entering state: **investigate** [feature] (run 1)
```

This format has two issues:
1. The machine-readable JSON is visually prominent at the beginning of comments
2. Even though `stokowski:route-error` already uses BASE64, it still uses the HTML comment format

**New format (at END of comment):**
```
**[Stokowski]** Entering state: **investigate** [feature] (run 1)

stokowski64:eyJzdGF0ZSI6ICJpbnZlc3RpZ2F0ZSIsICJydW4iOiAxLCAidGltZXN0YW1wIjogIjIwMjYtMDQtMTNUMTA6MTg6NDkuMTg5NjU5KzAwOjAwIiwgIndvcmtmbG93IjogImZlYXR1cmUifQ==
```

The new format uses a `stokowski64:` prefix followed by standard BASE64 encoding (no URL-safe variant needed as this stays in Linear comments).

## Goals / Non-Goals

**Goals:**
- Move machine-readable tracking data to the END of Linear comments for better readability
- Encode the entire marker (not just the JSON payload) in BASE64 for compactness
- Unify all marker types under a single `stokowski64:` format
- Maintain the same JSON payload structure internally (only the wrapper changes)
- Preserve existing timestamp-based ordering logic for determining "latest" tracking

**Non-Goals:**
- Backward compatibility with old format (clean migration is acceptable)
- Changing the JSON schema of tracking payloads
- URL-safe BASE64 encoding (standard BASE64 is sufficient for Linear)
- Compression beyond BASE64

## Decisions

### Decision 1: New Marker Format Structure
**Choice:** `stokowski64:<base64>` at end of comments

**Rationale:**
- Simple to parse: find last occurrence of `stokowski64:`, decode what follows
- BASE64 provides ~33% size reduction for JSON text
- No HTML comment syntax needed, avoiding `-->` parsing edge cases
- Easy to identify as "Stokowski machine data"

**Alternative considered:** Keep HTML comment wrapper with BASE64 inside
- Rejected: Still visually noisy, more complex parsing

### Decision 2: BASE64 Variant
**Choice:** Standard BASE64 (`base64.b64encode`)

**Rationale:**
- Linear comment field is plain text, no URL-encoding concerns
- Standard BASE64 is more compact than BASE64URL (no forced padding changes)
- Consistent with existing `stokowski:route-error` implementation

### Decision 3: Marker Placement
**Choice:** Append to END of comment

**Rationale:**
- Human-readable content comes first (better UX)
- Easy to implement: `human_text + "\n\n" + marker`
- Parsing still works: search for `stokowski64:` in entire body

### Decision 4: Unified Format for All Marker Types
**Choice:** All markers use `stokowski64:` with JSON containing `type` field

**Rationale:**
- Simpler codebase: one parsing function for all marker types
- JSON payloads include `"type": "state"|"gate"|"report"|"route_error"` for discrimination
- Eliminates special cases (like current route-error format)

### Decision 5: No Backward Compatibility
**Choice:** Clean migration - old format won't be parsed

**Rationale:**
- This is an internal format change, not an API contract
- Comments are ephemeral - old comments won't break, they just won't be "tracked"
- Maintaining dual parsers adds complexity for little benefit

## Risks / Trade-offs

**[Risk] In-flight issues may lose tracking context during deployment**
> **Mitigation:** This is acceptable - the orchestrator will re-discover active issues on next poll and start fresh tracking

**[Risk] BASE64 encoding makes debugging harder (can't read marker directly)**
> **Mitigation:** Human-readable text still explains the state; BASE64 is easily decodable when needed

**[Risk] Marker size limits in Linear**
> **Mitigation:** BASE64 reduces size by ~25%, and current payloads are small (<500 chars)

**[Risk] `stokowski64:` string might appear in legitimate comment content**
> **Mitigation:** Extremely unlikely; if needed, we can validate decoded JSON structure

## Migration Plan

1. **Phase 1 - Code Update:** Update all marker generation and parsing code
2. **Phase 2 - Test Update:** Update all test expectations to new format
3. **Phase 3 - Documentation Update:** Update AGENTS.md and any templates
4. **Phase 4 - Deployment:** Deploy new version; old markers will be ignored

**Rollback:** Revert to previous version if issues detected; old markers in existing comments won't be parsed but that's acceptable.

## Open Questions

None - design is ready for implementation.
