"""LinearClient.fetch_comments pagination."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, patch

import pytest

from stokowski.linear import COMMENTS_QUERY, LinearClient, LinearCommentsFetchError


@pytest.mark.asyncio
async def test_fetch_comments_pagination_merges_all_nodes():
    client = LinearClient("https://api.linear.app/graphql", "test-key")
    page1 = {
        "issue": {
            "comments": {
                "pageInfo": {"hasNextPage": True, "endCursor": "cursor_page1"},
                "nodes": [
                    {"id": "c1", "body": "first", "createdAt": "2026-01-01T00:00:00Z"},
                    {"id": "c2", "body": "second", "createdAt": "2026-01-02T00:00:00Z"},
                ],
            }
        }
    }
    page2 = {
        "issue": {
            "comments": {
                "pageInfo": {"hasNextPage": False, "endCursor": None},
                "nodes": [
                    {"id": "c3", "body": "third", "createdAt": "2026-01-03T00:00:00Z"},
                ],
            }
        }
    }

    with patch.object(client, "_graphql", new_callable=AsyncMock) as mock_gql:
        mock_gql.side_effect = [page1, page2]
        result = await client.fetch_comments("issue-uuid-123")

    assert result.complete is True
    assert len(result.nodes) == 3
    assert [c["id"] for c in result.nodes] == ["c1", "c2", "c3"]
    assert mock_gql.await_count == 2
    assert mock_gql.await_args_list[0].args[1] == {"issueId": "issue-uuid-123"}
    assert mock_gql.await_args_list[1].args[1] == {
        "issueId": "issue-uuid-123",
        "after": "cursor_page1",
    }


@pytest.mark.asyncio
async def test_fetch_comments_returns_partial_when_second_page_raises():
    client = LinearClient("https://api.linear.app/graphql", "test-key")
    page1 = {
        "issue": {
            "comments": {
                "pageInfo": {"hasNextPage": True, "endCursor": "c1"},
                "nodes": [{"id": "a", "body": "x", "createdAt": "2026-01-01T00:00:00Z"}],
            }
        }
    }

    with patch.object(client, "_graphql", new_callable=AsyncMock) as mock_gql:
        mock_gql.side_effect = [page1, RuntimeError("network")]
        result = await client.fetch_comments("issue-x")

    assert result.complete is False
    assert len(result.nodes) == 1
    assert result.nodes[0]["id"] == "a"


@pytest.mark.asyncio
async def test_fetch_comments_issue_null_returns_empty():
    client = LinearClient("https://api.linear.app/graphql", "test-key")
    with patch.object(client, "_graphql", new_callable=AsyncMock) as mock_gql:
        mock_gql.return_value = {"issue": None}
        result = await client.fetch_comments("missing")

    assert result.complete is True
    assert result.nodes == []


@pytest.mark.asyncio
async def test_fetch_comments_dedupes_duplicate_no_id_same_body_created_at():
    client = LinearClient("https://api.linear.app/graphql", "test-key")
    dup = {"body": "x", "createdAt": "2026-01-02T00:00:00Z"}
    page = {
        "issue": {
            "comments": {
                "pageInfo": {"hasNextPage": False, "endCursor": None},
                "nodes": [dup, dup],
            }
        }
    }
    with patch.object(client, "_graphql", new_callable=AsyncMock) as mock_gql:
        mock_gql.return_value = page
        result = await client.fetch_comments("issue-noid")
    assert len(result.nodes) == 1


@pytest.mark.asyncio
async def test_fetch_comments_dedupes_duplicate_ids_across_pages():
    client = LinearClient("https://api.linear.app/graphql", "test-key")
    dup = {"id": "same", "body": "b", "createdAt": "2026-01-02T00:00:00Z"}
    page1 = {
        "issue": {
            "comments": {
                "pageInfo": {"hasNextPage": True, "endCursor": "x"},
                "nodes": [dup],
            }
        }
    }
    page2 = {
        "issue": {
            "comments": {
                "pageInfo": {"hasNextPage": False, "endCursor": None},
                "nodes": [dup],
            }
        }
    }
    with patch.object(client, "_graphql", new_callable=AsyncMock) as mock_gql:
        mock_gql.side_effect = [page1, page2]
        result = await client.fetch_comments("issue-y")

    assert result.complete is True
    assert len(result.nodes) == 1
    assert result.nodes[0]["id"] == "same"


@pytest.mark.asyncio
async def test_fetch_comments_partial_when_has_next_without_end_cursor(caplog):
    """API oddity: log and return what we have."""
    client = LinearClient("https://api.linear.app/graphql", "test-key")
    page = {
        "issue": {
            "comments": {
                "pageInfo": {"hasNextPage": True, "endCursor": None},
                "nodes": [{"id": "only", "body": "x", "createdAt": "2026-01-01T00:00:00Z"}],
            }
        }
    }
    with patch.object(client, "_graphql", new_callable=AsyncMock) as mock_gql:
        mock_gql.return_value = page
        with caplog.at_level(logging.WARNING):
            out = await client.fetch_comments("issue-z")
    assert out.complete is False
    assert len(out.nodes) == 1
    assert out.nodes[0]["id"] == "only"
    assert "endCursor" in caplog.text


@pytest.mark.asyncio
async def test_fetch_comments_first_page_raises_linear_comments_fetch_error():
    client = LinearClient("https://api.linear.app/graphql", "test-key")
    with patch.object(client, "_graphql", new_callable=AsyncMock) as mock_gql:
        mock_gql.side_effect = RuntimeError("boom")
        with pytest.raises(LinearCommentsFetchError):
            await client.fetch_comments("issue-bad")


@pytest.mark.asyncio
async def test_fetch_comments_page_cap_returns_incomplete():
    client = LinearClient("https://api.linear.app/graphql", "test-key")
    page = {
        "issue": {
            "comments": {
                "pageInfo": {"hasNextPage": True, "endCursor": "c"},
                "nodes": [{"id": "x", "body": "y", "createdAt": "2026-01-01T00:00:00Z"}],
            }
        }
    }
    with (
        patch("stokowski.linear.MAX_COMMENT_PAGES", 2),
        patch.object(client, "_graphql", new_callable=AsyncMock) as mock_gql,
    ):
        mock_gql.return_value = page
        result = await client.fetch_comments("issue-cap")
    assert result.complete is False
    assert mock_gql.await_count == 2


def test_comments_query_does_not_use_order_by_on_issue_comments():
    """Regression guard: issue.comments rejects orderBy and returns HTTP 400."""
    assert "issue(id: $issueId)" in COMMENTS_QUERY
    assert "comments(first: 50, after: $after)" in COMMENTS_QUERY
    assert "orderBy" not in COMMENTS_QUERY
