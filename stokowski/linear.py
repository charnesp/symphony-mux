"""Linear API client for issue tracking."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

import httpx

from .datetime_parse import parse_linear_iso_datetime
from .models import BlockerRef, Issue

logger = logging.getLogger("stokowski.linear")

# Max GraphQL pages per issue for comments (50 comments per page).
MAX_COMMENT_PAGES = 500


@dataclass(frozen=True)
class CommentsFetchResult:
    """Result of ``LinearClient.fetch_comments``."""

    nodes: list[dict]
    complete: bool


class LinearCommentsFetchError(RuntimeError):
    """Raised when the first page of issue comments cannot be fetched."""


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
    comments(first: 50, after: $after, orderBy: createdAt) {
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


def _parse_datetime(val: str | None) -> datetime | None:
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


class LinearClient:
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

    async def close(self):
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
        self, project_slug: str, active_states: list[str]
    ) -> list[Issue]:
        """Fetch all issues in active states for the project."""
        issues: list[Issue] = []
        cursor = None

        while True:
            variables: dict = {
                "projectSlug": project_slug,
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

    async def fetch_issues_by_states(self, project_slug: str, states: list[str]) -> list[Issue]:
        """Fetch issues in specific states (for terminal cleanup)."""
        issues: list[Issue] = []
        cursor = None

        while True:
            variables: dict = {
                "projectSlug": project_slug,
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
