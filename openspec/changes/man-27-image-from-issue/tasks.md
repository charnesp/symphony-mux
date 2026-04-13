# Tasks: Image Support from Linear Issue Comments

## Implementation Phase

### Task 1: Extend Linear GraphQL Query
**Priority:** P0 (Blocking)  
**Estimated Time:** 30 min  
**Files:** `stokowski/linear.py`

- [ ] Update `COMMENTS_QUERY` to include `attachments` field
  - Add `attachments { nodes { id url title sourceType } }` to comment nodes
  - Ensure backwards compatibility (comments without attachments still work)
- [ ] Update test fixtures in `tests/test_linear_comments.py`
- [ ] Verify query works against Linear API (dry run)

**Definition of Done:**
- Query returns attachment data for comments with images
- Tests pass with new fixture data

---

### Task 2: Create Image Downloader
**Priority:** P0 (Blocking)  
**Estimated Time:** 1 hour  
**Files:** `stokowski/linear.py`

- [ ] Add `_download_image` helper method to `LinearClient`
  - Use existing httpx client with auth headers
  - Handle timeouts, retries, and errors gracefully
  - Validate downloaded file is an image (magic bytes)
- [ ] Add `download_comment_images` method
  - Filter for `sourceType == "image"` only
  - Create `images/` subdirectory in workspace
  - Generate safe filenames: `{issue_id}-{comment_id}-{sanitized_filename}`
  - Skip existing files (cache behavior)
  - Return updated comments with `downloaded_images` key
- [ ] Add helper `_get_mime_type` for file extension to MIME type mapping

**Definition of Done:**
- Images download successfully from Linear
- Files saved to correct location
- Failed downloads log warnings but don't break flow

---

### Task 3: Update Orchestrator to Download Images
**Priority:** P0 (Blocking)  
**Estimated Time:** 30 min  
**Files:** `stokowski/orchestrator.py`

- [ ] Modify `_load_issue_comments` to call `download_comment_images`
  - Pass `workspace_path` to the method
  - Only for LinearClient instances
- [ ] Ensure images are downloaded before prompt assembly
- [ ] Handle case where workspace doesn't exist yet (initial fetch)

**Definition of Done:**
- Comments loaded with image paths populated
- Images exist in workspace/images/ before agent runs

---

### Task 4: Embed Images in Prompts
**Priority:** P0 (Blocking)  
**Estimated Time:** 1 hour  
**Files:** `stokowski/prompt.py`

- [ ] Create `embed_images_in_prompt` helper function
  - Read image files from `downloaded_images` paths
  - Base64 encode images
  - Generate markdown image syntax with data URIs
  - Apply limits (max images per comment, max total)
- [ ] Update `build_lifecycle_context` to include image references
  - Add `has_images` boolean
  - Add `image_references` list for template use
- [ ] Update `assemble_prompt` to include embedded images in lifecycle section
  - Embed images as base64 data URIs in markdown
  - Place images after the relevant comment they belong to

**Definition of Done:**
- Prompt contains embedded base64 images
- Images appear in context of their comments
- Limits prevent excessive image embedding

---

### Task 5: Update Lifecycle Template (Optional)
**Priority:** P1 (Enhancement)  
**Estimated Time:** 30 min  
**Files:** `prompts/lifecycle.md` (or equivalent)

- [ ] Add conditional image display in lifecycle template
  - Show images inline with comments when present
  - Fallback for templates without image support
- [ ] Document image feature for template authors

**Definition of Done:**
- Default lifecycle template shows images
- Backwards compatible with old templates

---

### Task 6: Add Configuration Options
**Priority:** P1 (Enhancement)  
**Estimated Time:** 1 hour  
**Files:** `stokowski/config.py`

- [ ] Add optional `ImageConfig` dataclass
  - `enabled: bool = True`
  - `max_images_per_comment: int = 5`
  - `max_total_images: int = 20`
  - `max_image_size_mb: int = 10`
  - `supported_formats: list[str]`
- [ ] Integrate into `ServiceConfig`
- [ ] Apply config limits in image download and embedding

**Definition of Done:**
- Config options parsed from workflow.yaml
- Limits enforced during image processing

---

### Task 7: Write Tests
**Priority:** P0 (Blocking)  
**Estimated Time:** 2 hours  
**Files:** `tests/`

- [ ] Unit tests for `_download_image` method
  - Success case: image downloads
  - Failure case: handles HTTP errors
  - Validation: rejects non-image files
- [ ] Unit tests for `download_comment_images`
  - Multiple comments with images
  - Comments without attachments
  - Existing cached files (skip re-download)
- [ ] Unit tests for `embed_images_in_prompt`
  - Base64 encoding produces valid data URIs
  - Limits enforced (max per comment, max total)
  - Missing files handled gracefully
- [ ] Integration test for end-to-end flow
  - Mock Linear API response with attachments
  - Verify images embedded in prompt

**Definition of Done:**
- >80% test coverage for new code
- All edge cases tested
- Tests pass in CI

---

### Task 8: Update Documentation
**Priority:** P1 (Enhancement)  
**Estimated Time:** 30 min  
**Files:** `CLAUDE.md`, `README.md`

- [ ] Document image support feature in CLAUDE.md
- [ ] Update README with configuration options
- [ ] Add example workflow.yaml showing image config (optional)

**Definition of Done:**
- Documentation reflects new feature
- Configuration reference updated

---

### Task 9: Manual Testing
**Priority:** P0 (Blocking)  
**Estimated Time:** 1 hour  
**Files:** None (live testing)

- [ ] Create test issue with image attachments
- [ ] Run Stokowski locally with `--dry-run` to verify prompt
- [ ] Verify images appear in prompt output
- [ ] Verify Claude Code can process the images
- [ ] Test edge cases:
  - Multiple images in single comment
  - Large images (> 5MB)
  - Unsupported formats (should skip)

**Definition of Done:**
- Images successfully sent to Claude Code
- Agent can reference image content
- No regressions in text-only comments

---

## Summary

**Estimated Total Time:** ~8 hours  
**Key Dependencies:** Task 1 → Task 2 → Task 3 → Task 4  
**Nice-to-Have:** Tasks 5, 6, 8  
**Critical Path:** Tasks 1-4, 7, 9

## Risk Mitigation

1. **Linear API Changes:** If attachment schema differs from design:
   - Fall back gracefully (no images)
   - Log actual schema for debugging

2. **Claude Code Image Support:** If base64 images don't work:
   - Alternative: Use file paths with `--image` flag (if supported)
   - Alternative: Skip images and log warning

3. **Performance Issues:** If large images slow things down:
   - Implement size limits (Task 6)
   - Add image resizing before base64 encoding

4. **Memory Issues:** If base64 encoding consumes too much memory:
   - Stream images instead of loading all at once
   - Process images one at a time during prompt assembly
