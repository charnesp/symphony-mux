"""Linear API client for issue tracking."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from .datetime_parse import parse_linear_iso_datetime
from .models import BlockerRef, Issue
from .tracker import (
    CommentsFetchError,
    CommentsFetchResult,
    TrackerClient,
    TrackerConfig,
    TrackerFactory,
)

logger = logging.getLogger("stokowski.linear")

# Max GraphQL pages per issue for comments (50 comments per page).
MAX_COMMENT_PAGES = 500


class LinearCommentsFetchError(CommentsFetchError):
    """Raised when the first page of issue comments cannot be fetched.

    Backwards-compatible alias for CommentsFetchError.
    """


# Re-export CommentsFetchError for backwards compatibility
__all__ = [
    "LinearClient",
    "LinearCommentsFetchError",
    "LinearTrackerConfig",
    "CommentsFetchResult",
    "MAX_COMMENT_PAGES",
]


CANDIDATE_QUERY = """
query($projectSlug: String!, $states: [String!]!, $after: String) {
  issues(
    filter: {
      project: { slugId: { eq: $projectSlug } }
      state: { name: { in: $states } }
    }
    first: 50
    after: $after
    orderBy: createdAt
  ) {
    pageInfo {
      hasNextPage
      endCursor
    }
    nodes {
      id
      identifier
      title
      description
      priority
      url
      branchName
      createdAt
      updatedAt
      state { name }
      labels { nodes { name } }
      inverseRelations {
        nodes {
          type
          relatedIssue {
            id
            identifier
            state { name }
          }
        }
      }
    }
  }
}
"""

ISSUES_BY_IDS_QUERY = """
query($ids: [ID!]!) {
  issues(filter: { id: { in: $ids } }) {
    nodes {
      id
      identifier
      state { name }
    }
  }
}
"""

ISSUES_BY_STATES_QUERY = """
query($projectSlug: String!, $states: [String!]!, $after: String) {
  issues(
    filter: {
      project: { slugId: { eq: $projectSlug } }
      state: { name: { in: $states } }
    }
    first: 50
    after: $after
  ) {
    pageInfo {
      hasNextPage
      endCursor
    }
    nodes {
      id
      identifier
      state { name }
    }
  }
}
"""

COMMENT_CREATE_MUTATION = """
mutation($issueId: String!, $body: String!) {
  commentCreate(input: { issueId: $issueId, body: $body }) {
    success
    comment { id }
  }
}
"""

COMMENTS_QUERY = """
query($issueId: String!, $after: String) {
  issue(id: $issueId) {
    comments(first: 50, after: $after) {
      pageInfo {
        hasNextPage
        endCursor
      }
      nodes {
        id
        body
        createdAt
      }
    }
  }
}
"""

ISSUE_UPDATE_MUTATION = """
mutation($issueId: String!, $stateId: String!) {
  issueUpdate(id: $issueId, input: { stateId: $stateId }) {
    success
    issue { id state { name } }
  }
}
"""

ISSUE_TEAM_AND_STATES_QUERY = """
query($issueId: String!) {
  issue(id: $issueId) {
    team {
      id
      states {
        nodes {
          id
          name
        }
      }
    }
  }
}
"""


def _parse_datetime(val: str | None) -> Any:
    """Parse Linear datetimes to aware UTC (same rules as ``tracking``)."""
    return parse_linear_iso_datetime(val)


def _normalize_issue(node: dict) -> Issue:
    labels = [
        label["name"].lower()
        for label in (node.get("labels", {}) or {}).get("nodes", [])
        if label.get("name")
    ]

    blockers = []
    for rel in (node.get("inverseRelations", {}) or {}).get("nodes", []):
        if rel.get("type") == "blocks":
            ri = rel.get("relatedIssue", {}) or {}
            blockers.append(
                BlockerRef(
                    id=ri.get("id"),
                    identifier=ri.get("identifier"),
                    state=(ri.get("state") or {}).get("name"),
                )
            )

    priority = node.get("priority")
    if priority is not None:
        try:
            priority = int(priority)
        except (ValueError, TypeError):
            priority = None

    return Issue(
        id=node["id"],
        identifier=node["identifier"],
        title=node.get("title", ""),
        description=node.get("description"),
        priority=priority,
        state=(node.get("state") or {}).get("name", ""),
        branch_name=node.get("branchName"),
        url=node.get("url"),
        labels=labels,
        blocked_by=blockers,
        created_at=_parse_datetime(node.get("createdAt")),
        updated_at=_parse_datetime(node.get("updatedAt")),
    )


class LinearClient(TrackerClient):
    """Linear API client implementing the TrackerClient interface."""

    def __init__(self, endpoint: str, api_key: str, timeout_ms: int = 30_000):
        self.endpoint = endpoint
        self.api_key = api_key
        self.timeout = timeout_ms / 1000
        self._client = httpx.AsyncClient(
            headers={
                "Authorization": self.api_key,
                "Content-Type": "application/json",
            },
            timeout=self.timeout,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _graphql(self, query: str, variables: dict) -> dict:
        resp = await self._client.post(
            self.endpoint,
            json={"query": query, "variables": variables},
        )
        resp.raise_for_status()
        data = resp.json()
        if "errors" in data:
            raise RuntimeError(f"Linear GraphQL errors: {data['errors']}")
        return data.get("data", {})

    async def fetch_candidate_issues(
        self, project_id: str, active_states: list[str]
    ) -> list[Issue]:
        """Fetch all issues in active states for the project."""
        issues: list[Issue] = []
        cursor = None

        while True:
            variables: dict = {
                "projectSlug": project_id,
                "states": active_states,
            }
            if cursor:
                variables["after"] = cursor

            data = await self._graphql(CANDIDATE_QUERY, variables)
            issues_data = data.get("issues", {})
            nodes = issues_data.get("nodes", [])

            for node in nodes:
                try:
                    issues.append(_normalize_issue(node))
                except (KeyError, TypeError) as e:
                    logger.warning(f"Skipping malformed issue node: {e}")

            page_info = issues_data.get("pageInfo", {})
            if page_info.get("hasNextPage") and page_info.get("endCursor"):
                cursor = page_info["endCursor"]
            else:
                break

        return issues

    async def fetch_issue_states_by_ids(self, issue_ids: list[str]) -> dict[str, str]:
        """Fetch current states for given issue IDs. Returns {id: state_name}."""
        if not issue_ids:
            return {}

        data = await self._graphql(ISSUES_BY_IDS_QUERY, {"ids": issue_ids})
        result = {}
        for node in data.get("issues", {}).get("nodes", []):
            if node and node.get("id") and node.get("state"):
                result[node["id"]] = node["state"]["name"]
        return result

    async def fetch_issues_by_states(self, project_id: str, states: list[str]) -> list[Issue]:
        """Fetch issues in specific states (for terminal cleanup)."""
        issues: list[Issue] = []
        cursor = None

        while True:
            variables: dict = {
                "projectSlug": project_id,
                "states": states,
            }
            if cursor:
                variables["after"] = cursor

            data = await self._graphql(ISSUES_BY_STATES_QUERY, variables)
            issues_data = data.get("issues", {})
            for node in issues_data.get("nodes", []):
                if node and node.get("id"):
                    issues.append(
                        Issue(
                            id=node["id"],
                            identifier=node.get("identifier", ""),
                            title="",
                            state=(node.get("state") or {}).get("name", ""),
                        )
                    )

            page_info = issues_data.get("pageInfo", {})
            if page_info.get("hasNextPage") and page_info.get("endCursor"):
                cursor = page_info["endCursor"]
            else:
                break

        return issues

    async def post_comment(self, issue_id: str, body: str) -> bool:
        """Post a comment on a Linear issue. Returns True on success."""
        try:
            data = await self._graphql(
                COMMENT_CREATE_MUTATION,
                {"issueId": issue_id, "body": body},
            )
            return data.get("commentCreate", {}).get("success", False)
        except Exception as e:
            logger.error(f"Failed to post comment on {issue_id}: {e}")
            return False

    async def fetch_comments(self, issue_id: str) -> CommentsFetchResult:
        """Fetch all comments on a Linear issue.

        Returns ``CommentsFetchResult`` with ``nodes`` (each roughly
        ``{id, body, createdAt}``) and ``complete`` when the full history
        was loaded. Deduplicates by comment ``id`` when present, else by
        ``(body, createdAt)`` for nodes without an ``id``.

        Raises:
            LinearCommentsFetchError: GraphQL/network error before any page succeeds.

        After at least one successful page, errors or API anomalies yield
        ``complete=False`` with the nodes collected so far.
        """
        all_nodes: list[dict] = []
        seen_keys: set[tuple[object, ...]] = set()
        cursor: str | None = None
        got_successful_page = False
        pages_fetched = 0

        while True:
            if pages_fetched >= MAX_COMMENT_PAGES:
                logger.warning(
                    "Linear comments: page cap (%s) exceeded for issue %s; "
                    "stopping with partial history",
                    MAX_COMMENT_PAGES,
                    issue_id,
                )
                return CommentsFetchResult(all_nodes, False)

            variables: dict = {"issueId": issue_id}
            if cursor:
                variables["after"] = cursor

            try:
                data = await self._graphql(COMMENTS_QUERY, variables)
            except Exception as e:
                logger.error("Failed to fetch comments for %s: %s", issue_id, e)
                if not got_successful_page:
                    raise LinearCommentsFetchError(
                        f"Could not fetch comments for issue {issue_id}"
                    ) from e
                return CommentsFetchResult(all_nodes, False)

            got_successful_page = True
            pages_fetched += 1

            issue = data.get("issue") or {}
            conn = issue.get("comments") or {}
            raw_nodes = conn.get("nodes")
            if isinstance(raw_nodes, list):
                page_nodes = raw_nodes
            else:
                if raw_nodes is not None:
                    logger.warning("Linear comments: nodes is not a list for issue %s", issue_id)
                page_nodes = []

            for node in page_nodes:
                nid = node.get("id")
                if nid is not None:
                    key: tuple[object, ...] = ("id", str(nid))
                else:
                    body = node.get("body")
                    ca = node.get("createdAt")
                    key = (
                        "body_ca",
                        body if isinstance(body, str) else str(body),
                        ca if isinstance(ca, str) else str(ca),
                    )
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                all_nodes.append(node)

            page_info = conn.get("pageInfo") or {}
            has_next = bool(page_info.get("hasNextPage"))
            end_c = page_info.get("endCursor")
            if has_next and not end_c:
                logger.warning(
                    "Linear comments: hasNextPage set but endCursor missing for issue %s; "
                    "stopping with partial history",
                    issue_id,
                )
                return CommentsFetchResult(all_nodes, False)
            if has_next and end_c:
                cursor = end_c
            else:
                break

        return CommentsFetchResult(all_nodes, True)

    async def update_issue_state(self, issue_id: str, state_name: str) -> bool:
        """Move an issue to a new state by name. Returns True on success."""
        try:
            # Get team and its workflow states in one query
            data = await self._graphql(ISSUE_TEAM_AND_STATES_QUERY, {"issueId": issue_id})
            team = data.get("issue", {}).get("team", {})
            if not team:
                logger.error(f"Could not find team for issue {issue_id}")
                return False

            states = team.get("states", {}).get("nodes", [])
            state_id = None
            for s in states:
                if s.get("name", "").strip().lower() == state_name.strip().lower():
                    state_id = s["id"]
                    break

            if not state_id:
                logger.error(
                    f"State '{state_name}' not found. Available: {[s.get('name') for s in states]}"
                )
                return False

            # Update the issue
            result = await self._graphql(
                ISSUE_UPDATE_MUTATION,
                {"issueId": issue_id, "stateId": state_id},
            )
            success = result.get("issueUpdate", {}).get("success", False)
            if success:
                logger.info(f"Moved issue {issue_id} to state '{state_name}'")
            else:
                logger.error(f"Linear rejected state update for {issue_id}")
            return success
        except Exception as e:
            logger.error(f"Failed to update state for {issue_id}: {e}")
            return False

    # Image attachment handling
    _IMAGE_MAGIC_BYTES: dict[bytes, str] = {
        b"\x89PNG\r\n\x1a\n": "image/png",
        b"\xff\xd8\xff": "image/jpeg",
        b"GIF87a": "image/gif",
        b"GIF89a": "image/gif",
    }

    _EXTENSION_TO_MIME: dict[str, str] = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".heic": "image/heic",
        ".heif": "image/heic",
    }
    _MARKDOWN_IMAGE_PATTERN = re.compile(
        r"!\[(?P<title>[^\]]*)\]\(\s*(?:<)?(?P<url>https?://[^\s>)]+)(?:>)?(?:\s+\"[^\"]*\")?\s*\)"
    )
    _ALLOWED_IMAGE_HOSTS = {"files.linear.app", "uploads.linear.app"}

    @staticmethod
    def _get_mime_type(path: Path) -> str | None:
        """Determine MIME type from file extension."""
        ext = path.suffix.lower()
        return LinearClient._EXTENSION_TO_MIME.get(ext)

    @staticmethod
    def _is_webp(data: bytes) -> bool:
        """Check if data is a WebP image (RIFF....WEBP at offset 8)."""
        return len(data) >= 12 and data[0:4] == b"RIFF" and data[8:12] == b"WEBP"

    @staticmethod
    def _is_heic(data: bytes) -> bool:
        """Check if data is a HEIC/HEIF image (ISO Base Media File Format).

        HEIC uses ISO BMFF with 'ftyp' box at offset 4 and brand at offset 8.
        """
        if len(data) < 12:
            return False
        # ftyp box at offset 4
        if data[4:8] != b"ftyp":
            return False
        # Brand at offset 8
        brand = data[8:12]
        return brand in (b"heic", b"heix", b"mif1", b"msf1", b"hevc")

    @staticmethod
    def _validate_image_content(data: bytes) -> str | None:
        """Validate image content by magic bytes and return detected MIME type.

        Returns the MIME type if valid image, None otherwise.
        """
        # Check magic bytes
        for magic, mime in LinearClient._IMAGE_MAGIC_BYTES.items():
            if data.startswith(magic):
                return mime

        # Check WebP (requires length >= 12 for complete validation)
        if LinearClient._is_webp(data):
            return "image/webp"

        # Check HEIC/HEIF (ISO BMFF format)
        if LinearClient._is_heic(data):
            return "image/heic"

        return None

    @staticmethod
    def _extract_markdown_image_attachments(body: str | None) -> list[dict[str, str]]:
        """Extract markdown image URLs from comment body.

        Returns attachment-like dicts to keep the downstream image download
        pipeline unchanged when the GraphQL ``Comment`` type does not expose
        ``attachments``.
        """
        if not body:
            return []

        out: list[dict[str, str]] = []
        seen_urls: set[str] = set()
        for match in LinearClient._MARKDOWN_IMAGE_PATTERN.finditer(body):
            url = (match.group("url") or "").strip()
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            title = (match.group("title") or "").strip() or Path(url).name or "image"
            out.append(
                {
                    "url": url,
                    "title": title,
                    "sourceType": "image",
                }
            )
        return out

    @staticmethod
    def _is_allowed_image_url(url: str) -> bool:
        """Allow only HTTPS URLs on Linear-owned upload domains."""
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        return parsed.scheme == "https" and host in LinearClient._ALLOWED_IMAGE_HOSTS

    async def _download_image(self, url: str, dest_path: Path) -> bool:
        """Download image from Linear and save to dest_path.

        Args:
            url: The image URL from Linear attachment
            dest_path: Where to save the downloaded image

        Returns:
            True if download succeeded and content is valid image, False otherwise
        """
        try:
            if not self._is_allowed_image_url(url):
                logger.warning("Rejected non-Linear image URL: %s", url)
                return False

            # Use existing httpx client with auth headers
            headers = {"Authorization": self.api_key}
            response = await self._client.get(url, headers=headers, timeout=30)
            response.raise_for_status()

            data = response.content

            # Validate it's an actual image
            detected_mime = self._validate_image_content(data)
            if not detected_mime:
                logger.warning(
                    "Downloaded file from %s is not a valid image (magic bytes check failed)",
                    url,
                )
                return False

            # Write to destination
            dest_path.write_bytes(data)
            logger.debug(
                "Downloaded image to %s (%s, %d bytes)", dest_path, detected_mime, len(data)
            )
            return True

        except httpx.TimeoutException:
            logger.warning("Timeout downloading image from %s", url)
            return False
        except httpx.HTTPStatusError as e:
            logger.warning("HTTP error downloading image from %s: %s", url, e.response.status_code)
            return False
        except Exception as e:
            logger.warning("Failed to download image from %s: %s", url, e)
            return False

    async def download_comment_images(
        self,
        comments: list[dict],
        issue: Issue,
        workspace_path: Path,
        max_images_per_comment: int = 5,
        max_total_images: int = 20,
        max_image_size_mb: int = 10,
    ) -> list[dict]:
        """Download images from comment attachments or markdown image links.

        Prefers ``comment.attachments.nodes`` when available. For API schemas
        where ``Comment`` has no ``attachments`` field, falls back to extracting
        markdown image links from ``comment.body``.

        Downloads images to workspace/images/ with filenames like
        {issue_identifier}-{comment_id}-{sanitized_filename}. Skips existing
        files (cache behavior).

        Args:
            comments: List of comment nodes from fetch_comments
            issue: The issue being processed
            workspace_path: Path to the issue's workspace directory
            max_images_per_comment: Maximum images to download per comment
            max_total_images: Maximum total images across all comments
            max_image_size_mb: Maximum image size in MB to download

        Returns:
            Comments with added 'downloaded_images' key containing list of dicts
            with 'path', 'url', 'title', 'mime_type' for each downloaded image.
        """
        images_dir = workspace_path / "images"
        images_dir.mkdir(parents=True, exist_ok=True)

        total_count = 0
        max_size_bytes = max_image_size_mb * 1024 * 1024

        for comment in comments:
            attachments = comment.get("attachments", {}).get("nodes", [])
            if not attachments:
                attachments = self._extract_markdown_image_attachments(comment.get("body"))
            downloaded = []

            for attachment in attachments[:max_images_per_comment]:
                if total_count >= max_total_images:
                    logger.debug("Reached max_total_images limit (%d)", max_total_images)
                    break

                # Only process image attachments
                if attachment.get("sourceType") != "image":
                    continue

                url = attachment.get("url")
                if not url:
                    continue

                # Build safe filename
                comment_id = comment.get("id", "unknown")[:8]
                filename = attachment.get("title", "image")
                # Sanitize filename - replace non-alphanumeric with underscore
                safe_filename = "".join(c if c.isalnum() or c in "._-" else "_" for c in filename)
                # Handle edge cases: empty or dot-only names
                safe_filename = safe_filename.strip("._")
                if not safe_filename:
                    safe_filename = "image"
                # Ensure it has a reasonable extension
                if not Path(safe_filename).suffix:
                    safe_filename += ".png"
                dest_name = f"{issue.identifier}-{comment_id}-{safe_filename}"
                dest_path = images_dir / dest_name

                # Check file size if it exists
                if dest_path.exists():
                    file_size = dest_path.stat().st_size
                    if file_size > max_size_bytes:
                        logger.warning(
                            "Cached image %s exceeds size limit (%d > %d bytes), skipping",
                            dest_path.name,
                            file_size,
                            max_size_bytes,
                        )
                        continue
                    # Use cached file
                    mime_type = self._get_mime_type(dest_path)
                    downloaded.append(
                        {
                            "path": str(dest_path),
                            "url": url,
                            "title": filename,
                            "mime_type": mime_type or "image/png",
                        }
                    )
                    total_count += 1
                    continue

                # Download new file
                if await self._download_image(url, dest_path):
                    # Verify size after download
                    file_size = dest_path.stat().st_size
                    if file_size > max_size_bytes:
                        logger.warning(
                            "Downloaded image %s exceeds size limit (%d > %d bytes), removing",
                            dest_path.name,
                            file_size,
                            max_size_bytes,
                        )
                        dest_path.unlink(missing_ok=True)
                        continue

                    mime_type = self._get_mime_type(dest_path)
                    downloaded.append(
                        {
                            "path": str(dest_path),
                            "url": url,
                            "title": filename,
                            "mime_type": mime_type or "image/png",
                        }
                    )
                    total_count += 1

            comment["downloaded_images"] = downloaded

        return comments


@dataclass
class LinearTrackerConfig(TrackerConfig):
    """Configuration for Linear tracker."""

    endpoint: str = "https://api.linear.app/graphql"
    api_key: str = ""
    project_slug: str = ""
    timeout_ms: int = 30_000

    @classmethod
    def from_dict(cls, config: dict[str, Any]) -> LinearTrackerConfig:
        """Create configuration from dictionary."""
        return cls(
            endpoint=config.get("endpoint", "https://api.linear.app/graphql"),
            api_key=config.get("api_key", ""),
            project_slug=config.get("project_slug", ""),
            timeout_ms=config.get("timeout_ms", 30_000),
        )

    def create_client(self) -> TrackerClient:
        """Create and return a LinearClient instance."""
        return LinearClient(
            endpoint=self.endpoint,
            api_key=self.api_key,
            timeout_ms=self.timeout_ms,
        )


# Register with the tracker factory
TrackerFactory.register("linear", LinearTrackerConfig)
