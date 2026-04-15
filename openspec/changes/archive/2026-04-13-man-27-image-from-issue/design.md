# Design: Image Support from Linear Issue Comments

## Architecture Overview

```
┌───────────────┐     ┌───────────────┐     ┌───────────────┐     ┌───────────────┐
│  Linear API   │────▶│ Image Fetcher │────▶│  Temp Storage │────▶│  Claude Code  │
│  (GraphQL)    │     │   (httpx)     │     │  (workspace)  │     │  (CLI stdin)  │
└───────────────┘     └───────────────┘     └───────────────┘     └───────────────┘
```

## Linear GraphQL Schema Changes

### Comment Query Extension

The `COMMENTS_QUERY` needs to include attachment data:

```graphql
query($issueId: String!, $after: String) {
  issue(id: $issueId) {
    comments(first: 50, after: $after, orderBy: createdAt) {
      pageInfo {
        hasNextPage
        endCursor
      }
      nodes {
        id
        body
        createdAt
        attachments {
          nodes {
            id
            url
            title
            source
            sourceType
          }
        }
      }
    }
  }
}
```

**Key Fields:**
- `attachments`: List of file attachments on the comment
- `url`: Direct URL to download the file (requires auth headers)
- `sourceType`: Type of attachment (e.g., "image", "file")
- `title`: Filename or description

## Data Model Changes

### New: `CommentAttachment` dataclass

```python
@dataclass
class CommentAttachment:
    id: str
    url: str
    title: str
    source_type: str  # "image" or "file"
    local_path: Path | None = None  # Populated after download
```

### Updated: Comment structure

The `fetch_comments` method returns nodes with an `attachments` key:

```python
{
    "id": "comment-uuid",
    "body": "comment text",
    "createdAt": "2026-01-01T00:00:00Z",
    "attachments": {
        "nodes": [
            {
                "id": "attachment-uuid",
                "url": "https://files.linear.app/...",
                "title": "screenshot.png",
                "sourceType": "image"
            }
        ]
    }
}
```

## Image Download Strategy

### Storage Location

Images are stored in the per-issue workspace directory:
```
workspace/
  MAN-27/
    .git/               # Cloned repo
    images/             # Downloaded comment images
      MAN-27-comment-uuid-1_screenshot.png
      MAN-27-comment-uuid-2_diagram.jpg
```

### Download Process

1. **Timing**: Images are downloaded after comments are fetched, during `_load_issue_comments`
2. **Authentication**: Reuse the Linear API key from the client headers
3. **Filtering**: Only download `sourceType == "image"` attachments
4. **Naming**: `{issue_identifier}-{comment_id}-{sanitized_filename}`
5. **Deduplication**: Skip download if file already exists (by path)

### Supported Image Formats

- PNG (image/png)
- JPEG/JPG (image/jpeg)
- GIF (image/gif)
- WebP (image/webp)
- HEIC (optional, may require conversion)

## Prompt Integration

### Current Comment Formatting

Comments are included in prompts via the lifecycle template. Example from current implementation:

```markdown
### Recent Comments (since last run)

**2026-01-01 10:30 UTC** - user@example.com:
This is the comment body text.
```

### Proposed Format with Images

```markdown
### Recent Comments (since last run)

**2026-01-01 10:30 UTC** - user@example.com:
This is the comment body text.

**Attachments:**
- [Image: screenshot.png](file:///path/to/workspace/images/MAN-27-comment-uuid_screenshot.png)

![screenshot.png](file:///path/to/workspace/images/MAN-27-comment-uuid_screenshot.png)
```

### Claude Code Image Input

Claude Code CLI accepts images via:

**Option 1: Base64 Data URI in prompt text**
```markdown
![Description](data:image/png;base64,iVBORw0KGgo...)
```

**Option 2: File path references** (not directly supported by CLI)

**Chosen Approach: Base64 embedded images**

Since Claude Code receives prompts via stdin as text, images must be embedded as base64 data URIs in the markdown.

**Optimization:** Only embed images referenced in recent comments (not all historical images).

## Implementation Plan

### Phase 1: Linear API Changes

**File: `stokowski/linear.py`**

1. Update `COMMENTS_QUERY` to include `attachments` field
2. Create `ImageDownloader` class:
   ```python
   class ImageDownloader:
       def __init__(self, api_key: str, http_client: httpx.AsyncClient):
           self.api_key = api_key
           self.client = http_client

       async def download_image(self, url: str, dest_path: Path) -> bool:
           """Download image from Linear, return success."""
           try:
               headers = {"Authorization": self.api_key}
               response = await self.client.get(url, headers=headers, timeout=30)
               response.raise_for_status()
               dest_path.write_bytes(response.content)
               return True
           except Exception as e:
               logger.warning(f"Failed to download image: {e}")
               return False
   ```

3. Add `download_comment_images` method to `LinearClient`:
   ```python
   async def download_comment_images(
       self,
       comments: list[dict],
       issue: Issue,
       workspace_path: Path
   ) -> list[dict]:
       """Download images from comment attachments.

       Returns comments with added 'downloaded_images' key containing list of local paths.
       """
       images_dir = workspace_path / "images"
       images_dir.mkdir(exist_ok=True)

       for comment in comments:
           attachments = comment.get("attachments", {}).get("nodes", [])
           downloaded = []

           for attachment in attachments:
               if attachment.get("sourceType") != "image":
                   continue

               url = attachment.get("url")
               if not url:
                   continue

               # Build filename
               comment_id = comment.get("id", "unknown")[:8]
               filename = attachment.get("title", "image")
               safe_filename = re.sub(r"[^\w.-]", "_", filename)
               dest_name = f"{issue.identifier}-{comment_id}-{safe_filename}"
               dest_path = images_dir / dest_name

               # Download if not exists
               if not dest_path.exists():
                   if await self._download_image(url, dest_path):
                       downloaded.append(str(dest_path))
               else:
                   downloaded.append(str(dest_path))

           comment["downloaded_images"] = downloaded

       return comments
   ```

### Phase 2: Prompt Assembly Changes

**File: `stokowski/prompt.py`**

1. Modify `assemble_prompt` signature to accept images:
   ```python
   def assemble_prompt(
       ...,
       comments: list[dict] | None = None,
       include_images: bool = True,  # New parameter
   ) -> tuple[str, list[Path]]:  # Returns (prompt, image_paths)
   ```

2. Create `embed_images_in_prompt` helper:
   ```python
   def embed_images_in_prompt(
       comments: list[dict],
       max_images_per_comment: int = 5,
       max_total_images: int = 20
   ) -> str:
       """Generate markdown with embedded base64 images."""
       image_markdown = []
       total_count = 0

       for comment in comments:
           images = comment.get("downloaded_images", [])
           for img_path in images[:max_images_per_comment]:
               if total_count >= max_total_images:
                   break

               path = Path(img_path)
               if not path.exists():
                   continue

               # Read and encode
               data = path.read_bytes()
               mime_type = _get_mime_type(path)
               b64 = base64.b64encode(data).decode()

               # Add markdown image
               image_markdown.append(
                   f"![{path.name}](data:{mime_type};base64,{b64})"
               )
               total_count += 1

       return "\n".join(image_markdown)
   ```

3. Update lifecycle template context to include images:
   ```python
   context.update({
       "has_images": any(c.get("downloaded_images") for c in comments),
       "image_references": build_image_references(comments),
   })
   ```

### Phase 3: Orchestrator Integration

**File: `stokowski/orchestrator.py`**

1. Modify `_load_issue_comments` to download images:
   ```python
   async def _load_issue_comments(
       self,
       client: LinearClient,
       issue: Issue,
       workspace_path: Path
   ) -> list[dict]:
       result = await client.fetch_comments(issue.id)
       comments = result.nodes

       # Download images from attachments
       if isinstance(client, LinearClient):
           comments = await client.download_comment_images(
               comments, issue, workspace_path
           )

       return comments
   ```

### Phase 4: Runner Integration

**File: `stokowski/runner.py`**

Currently, images are passed via the prompt text (base64 embedded). No changes needed to runner if we use embedded base64 approach.

Alternative: If using file paths, would need to pass `--images` flag or similar (not currently supported in Claude Code CLI).

**Decision:** Use base64 embedded images in prompt markdown.

### Phase 5: Configuration Options

**Optional: Add to `config.py`**

```python
@dataclass
class ImageConfig:
    enabled: bool = True
    max_images_per_comment: int = 5
    max_total_images: int = 20
    max_image_size_mb: int = 10
    supported_formats: list[str] = field(default_factory=lambda: ["png", "jpg", "jpeg", "gif", "webp"])
```

## Error Handling

### Download Failures
- Log warning, continue without image
- Comment still included in prompt (text only)

### Unsupported Formats
- Skip with warning
- Only attempt to download known image formats

### Size Limits
- Skip images > max_image_size_mb
- Prevents excessive memory usage

### Missing Attachments
- Gracefully handle comments without attachments key (backwards compatibility)

## Testing Strategy

### Unit Tests
1. Mock Linear GraphQL response with attachments
2. Test image download with mocked httpx
3. Test base64 encoding of images
4. Test prompt assembly with images

### Integration Tests
1. Fetch real issue with images (manual)
2. Verify prompt contains embedded images
3. Verify Claude Code can process the images

### Edge Cases
1. Comment with multiple images
2. Image download timeout
3. Corrupted image file
4. Very large image (exceeds limit)
5. Non-image attachments (should be skipped)

## Performance Considerations

### Network
- Images downloaded in parallel using `asyncio.gather`
- Linear's CDN serves images quickly

### Memory
- Images streamed to disk, not held in memory
- Base64 encoding done at prompt assembly time
- Total prompt size increase: ~1.3x per image (base64 overhead)

### Caching
- Images cached in workspace directory
- Re-download only if file doesn't exist
- Workspace cleanup removes images with issue completion

## Security Considerations

### Authentication
- Linear API key required for image downloads
- URL tokens may have expiration - ensure fresh download

### File Validation
- Verify downloaded files are valid images (magic number check)
- Prevent path traversal in filenames
- Sanitize filenames before writing

### Privacy
- Images stored in workspace (same security as code)
- No external image hosting

## Migration Path

1. No breaking changes - existing configs work unchanged
2. Images feature auto-enabled when attachments present
3. Can disable via config if needed (future)

## Future Enhancements

1. **Image Description**: Generate alt-text using vision model
2. **Deduplication**: Hash-based dedup across issues
3. **Resizing**: Auto-resize large images before embedding
4. **Caching Layer**: Shared image cache across issues
5. **Video Support**: Extract frames from video attachments
