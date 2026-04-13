# Proposal: Image Support from Linear Issue Comments

## Overview
Enable Stokowski to fetch images attached to Linear issue comments and include them in prompts sent to the LLM (Claude Code). This allows agents to view screenshots, diagrams, and other visual context attached to issues.

## Problem Statement
Currently, Stokowski only fetches the text body of Linear comments. When users attach images (screenshots, mockups, diagrams) to provide visual context, this information is lost to the agent. This limits the agent's ability to understand and work on issues that rely on visual information.

## Goals
1. Fetch image attachments from Linear issue comments via GraphQL API
2. Download image files to a temporary/cache location
3. Include images in prompts to Claude Code in a format it can process
4. Support common image formats (PNG, JPG, GIF, WebP)
5. Handle errors gracefully (failed downloads, unsupported formats)

## Non-Goals
- Video or audio attachments (out of scope for initial implementation)
- Image processing (resizing, format conversion) - use original files
- OCR or text extraction from images - LLM handles this
- Storage optimization/deduplication of images

## Use Cases
1. **Bug Reports**: User attaches screenshot showing the error; agent sees and understands the visual bug
2. **UI/UX Tasks**: User attaches mockup or design reference; agent implements based on visual reference
3. **Architecture Diagrams**: User attaches system diagram; agent understands the architecture
4. **Visual Testing**: Agent can see expected vs actual visual output

## Success Criteria
- Images in Linear comments are fetched and included in agent prompts
- Claude Code can view and reference the images in its responses
- No breaking changes to existing comment handling
- Graceful degradation when images fail to download
- Performance: image fetching adds <2s to comment loading time

## Affected Components
- `stokowski/linear.py` - GraphQL query modifications
- `stokowski/tracker.py` - Attachment model definitions
- `stokowski/prompt.py` - Prompt assembly with images
- `stokowski/runner.py` - Image passing to Claude Code
- `stokowski/config.py` - Optional: image size limits

## Backwards Compatibility
Fully backwards compatible. Existing text-only comments continue to work unchanged. Image support is additive only.
