"""Tests for Linear image attachment handling."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from stokowski.linear import LinearClient
from stokowski.models import Issue


@pytest.mark.asyncio
async def test_download_image_success(tmp_path: Path):
    """Test successful image download."""
    client = LinearClient("https://api.linear.app/graphql", "test-key")
    dest_path = tmp_path / "test.png"

    # PNG file header
    png_data = b"\x89PNG\r\n\x1a\n" + b"fake png data"

    mock_response = AsyncMock()
    mock_response.content = png_data
    mock_response.raise_for_status = AsyncMock()

    with patch.object(client._client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response
        result = await client._download_image("https://example.com/image.png", dest_path)

    assert result is True
    assert dest_path.exists()
    assert dest_path.read_bytes() == png_data


@pytest.mark.asyncio
async def test_download_image_invalid_content(tmp_path: Path):
    """Test download rejection of non-image content."""
    client = LinearClient("https://api.linear.app/graphql", "test-key")
    dest_path = tmp_path / "test.txt"

    # Non-image data
    fake_data = b"this is not an image file"

    mock_response = AsyncMock()
    mock_response.content = fake_data
    mock_response.raise_for_status = AsyncMock()

    with patch.object(client._client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response
        result = await client._download_image("https://example.com/file.txt", dest_path)

    assert result is False
    assert not dest_path.exists()


@pytest.mark.asyncio
async def test_download_image_http_error(tmp_path: Path):
    """Test handling of HTTP error during download."""
    client = LinearClient("https://api.linear.app/graphql", "test-key")
    dest_path = tmp_path / "test.png"

    mock_response = AsyncMock()
    mock_response.raise_for_status = AsyncMock(side_effect=Exception("HTTP 404"))

    with patch.object(client._client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response
        result = await client._download_image("https://example.com/missing.png", dest_path)

    assert result is False


@pytest.mark.asyncio
async def test_download_image_timeout(tmp_path: Path):
    """Test handling of timeout during download."""
    client = LinearClient("https://api.linear.app/graphql", "test-key")
    dest_path = tmp_path / "test.png"

    import httpx

    with patch.object(client._client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = httpx.TimeoutException("Connection timeout")
        result = await client._download_image("https://example.com/slow.png", dest_path)

    assert result is False


@pytest.mark.asyncio
async def test_download_comment_images_no_attachments(tmp_path: Path):
    """Test download_comment_images with no attachments."""
    client = LinearClient("https://api.linear.app/graphql", "test-key")
    issue = Issue(
        id="issue-123",
        identifier="MAN-27",
        title="Test Issue",
    )
    comments = [{"id": "c1", "body": "No attachments here", "createdAt": "2026-01-01T00:00:00Z"}]

    result = await client.download_comment_images(comments, issue, tmp_path)

    assert len(result) == 1
    assert result[0]["downloaded_images"] == []


@pytest.mark.asyncio
async def test_download_comment_images_with_image_attachments(tmp_path: Path):
    """Test downloading images from comment attachments."""
    client = LinearClient("https://api.linear.app/graphql", "test-key")
    issue = Issue(
        id="issue-123",
        identifier="MAN-27",
        title="Test Issue",
    )

    # PNG file header
    png_data = b"\x89PNG\r\n\x1a\n" + b"fake png data"

    comments = [
        {
            "id": "c1",
            "body": "Check this screenshot",
            "createdAt": "2026-01-01T00:00:00Z",
            "attachments": {
                "nodes": [
                    {
                        "id": "att-1",
                        "url": "https://files.linear.app/image.png",
                        "title": "screenshot.png",
                        "sourceType": "image",
                    }
                ]
            },
        }
    ]

    mock_response = AsyncMock()
    mock_response.content = png_data
    mock_response.raise_for_status = AsyncMock()

    with patch.object(client._client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response
        result = await client.download_comment_images(comments, issue, tmp_path)

    assert len(result) == 1
    assert len(result[0]["downloaded_images"]) == 1

    img_info = result[0]["downloaded_images"][0]
    assert img_info["url"] == "https://files.linear.app/image.png"
    assert img_info["title"] == "screenshot.png"
    assert img_info["mime_type"] == "image/png"
    assert Path(img_info["path"]).exists()


@pytest.mark.asyncio
async def test_download_comment_images_skips_non_image_attachments(tmp_path: Path):
    """Test that non-image attachments are skipped."""
    client = LinearClient("https://api.linear.app/graphql", "test-key")
    issue = Issue(
        id="issue-123",
        identifier="MAN-27",
        title="Test Issue",
    )

    comments = [
        {
            "id": "c1",
            "body": "Attached a file",
            "createdAt": "2026-01-01T00:00:00Z",
            "attachments": {
                "nodes": [
                    {
                        "id": "att-1",
                        "url": "https://files.linear.app/doc.pdf",
                        "title": "document.pdf",
                        "sourceType": "file",  # Not "image"
                    }
                ]
            },
        }
    ]

    result = await client.download_comment_images(comments, issue, tmp_path)

    assert len(result) == 1
    assert result[0]["downloaded_images"] == []


@pytest.mark.asyncio
async def test_download_comment_images_caches_existing_files(tmp_path: Path):
    """Test that existing cached files are not re-downloaded."""
    client = LinearClient("https://api.linear.app/graphql", "test-key")
    issue = Issue(
        id="issue-123",
        identifier="MAN-27",
        title="Test Issue",
    )

    # Create existing file
    images_dir = tmp_path / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    existing_file = images_dir / "MAN-27-c1-screenshot.png"
    existing_file.write_bytes(b"\x89PNG\r\n\x1a\nexisting data")

    comments = [
        {
            "id": "c1",
            "body": "Check this screenshot",
            "createdAt": "2026-01-01T00:00:00Z",
            "attachments": {
                "nodes": [
                    {
                        "id": "att-1",
                        "url": "https://files.linear.app/image.png",
                        "title": "screenshot.png",
                        "sourceType": "image",
                    }
                ]
            },
        }
    ]

    # Should not make HTTP request because file exists
    with patch.object(client._client, "get") as mock_get:
        result = await client.download_comment_images(comments, issue, tmp_path)
        mock_get.assert_not_called()

    assert len(result) == 1
    assert len(result[0]["downloaded_images"]) == 1


@pytest.mark.asyncio
async def test_download_comment_images_respects_limits(tmp_path: Path):
    """Test that max limits are respected."""
    client = LinearClient("https://api.linear.app/graphql", "test-key")
    issue = Issue(
        id="issue-123",
        identifier="MAN-27",
        title="Test Issue",
    )

    # Create multiple attachments
    attachments = [
        {
            "id": f"att-{i}",
            "url": f"https://files.linear.app/image{i}.png",
            "title": f"screenshot{i}.png",
            "sourceType": "image",
        }
        for i in range(10)
    ]

    comments = [
        {
            "id": "c1",
            "body": "Many images",
            "createdAt": "2026-01-01T00:00:00Z",
            "attachments": {"nodes": attachments},
        }
    ]

    png_data = b"\x89PNG\r\n\x1a\n" + b"fake png data"
    mock_response = AsyncMock()
    mock_response.content = png_data
    mock_response.raise_for_status = AsyncMock()

    with patch.object(client._client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response
        result = await client.download_comment_images(
            comments, issue, tmp_path, max_images_per_comment=3, max_total_images=5
        )

    assert len(result[0]["downloaded_images"]) == 3  # Limited by max_images_per_comment


@pytest.mark.asyncio
async def test_download_comment_images_respects_size_limit(tmp_path: Path):
    """Test that oversized images are skipped."""
    client = LinearClient("https://api.linear.app/graphql", "test-key")
    issue = Issue(
        id="issue-123",
        identifier="MAN-27",
        title="Test Issue",
    )

    # Create a large file (simulating download)
    png_data = b"\x89PNG\r\n\x1a\n" + b"x" * (20 * 1024 * 1024)  # 20MB+ data

    comments = [
        {
            "id": "c1",
            "body": "Large image",
            "createdAt": "2026-01-01T00:00:00Z",
            "attachments": {
                "nodes": [
                    {
                        "id": "att-1",
                        "url": "https://files.linear.app/huge.png",
                        "title": "huge.png",
                        "sourceType": "image",
                    }
                ]
            },
        }
    ]

    mock_response = AsyncMock()
    mock_response.content = png_data
    mock_response.raise_for_status = AsyncMock()

    with patch.object(client._client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response
        result = await client.download_comment_images(
            comments, issue, tmp_path, max_image_size_mb=10
        )

    assert len(result[0]["downloaded_images"]) == 0  # Skipped due to size


def test_get_mime_type_from_path():
    """Test MIME type detection from file extension."""
    assert LinearClient._get_mime_type(Path("image.png")) == "image/png"
    assert LinearClient._get_mime_type(Path("image.jpg")) == "image/jpeg"
    assert LinearClient._get_mime_type(Path("image.jpeg")) == "image/jpeg"
    assert LinearClient._get_mime_type(Path("image.gif")) == "image/gif"
    assert LinearClient._get_mime_type(Path("image.webp")) == "image/webp"
    assert LinearClient._get_mime_type(Path("image.heic")) == "image/heic"
    assert LinearClient._get_mime_type(Path("image.UNKNOWN")) is None


def test_validate_image_content():
    """Test image validation by magic bytes."""
    # Valid images
    assert LinearClient._validate_image_content(b"\x89PNG\r\n\x1a\n") == "image/png"
    assert LinearClient._validate_image_content(b"\xff\xd8\xff") == "image/jpeg"
    assert LinearClient._validate_image_content(b"GIF87a") == "image/gif"
    assert LinearClient._validate_image_content(b"GIF89a") == "image/gif"

    # WebP with RIFF....WEBP
    webp_data = b"RIFF\x00\x00\x00\x00WEBPVP8"
    assert LinearClient._validate_image_content(webp_data) == "image/webp"

    # Invalid
    assert LinearClient._validate_image_content(b"not an image") is None
    assert LinearClient._validate_image_content(b"") is None


@pytest.mark.asyncio
async def test_download_comment_images_missing_url(tmp_path: Path):
    """Test handling of attachment without URL."""
    client = LinearClient("https://api.linear.app/graphql", "test-key")
    issue = Issue(
        id="issue-123",
        identifier="MAN-27",
        title="Test Issue",
    )

    comments = [
        {
            "id": "c1",
            "body": "Broken attachment",
            "createdAt": "2026-01-01T00:00:00Z",
            "attachments": {
                "nodes": [
                    {
                        "id": "att-1",
                        "url": None,  # Missing URL
                        "title": "broken.png",
                        "sourceType": "image",
                    }
                ]
            },
        }
    ]

    result = await client.download_comment_images(comments, issue, tmp_path)

    assert len(result) == 1
    assert result[0]["downloaded_images"] == []


@pytest.mark.asyncio
async def test_download_comment_images_from_markdown_body(tmp_path: Path):
    """Extract image URLs from markdown body when attachments are unavailable."""
    client = LinearClient("https://api.linear.app/graphql", "test-key")
    issue = Issue(
        id="issue-123",
        identifier="MAN-27",
        title="Test Issue",
    )

    comments = [
        {
            "id": "c1",
            "body": "Screenshot:\\n![screen](https://files.linear.app/screen.png)",
            "createdAt": "2026-01-01T00:00:00Z",
        }
    ]

    png_data = b"\x89PNG\r\n\x1a\n" + b"fake png data"
    mock_response = AsyncMock()
    mock_response.content = png_data
    mock_response.raise_for_status = AsyncMock()

    with patch.object(client._client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response
        result = await client.download_comment_images(comments, issue, tmp_path)

    assert len(result) == 1
    assert len(result[0]["downloaded_images"]) == 1
    img_info = result[0]["downloaded_images"][0]
    assert img_info["url"] == "https://files.linear.app/screen.png"
    assert img_info["title"] == "screen"
    assert Path(img_info["path"]).exists()


def test_extract_markdown_image_attachments():
    """Markdown image syntax should be converted into image attachment-like entries."""
    body = (
        "See image ![A](https://files.linear.app/a.png) and "
        "![B](https://files.linear.app/b.webp) plus duplicate "
        "![A2](https://files.linear.app/a.png)"
    )
    out = LinearClient._extract_markdown_image_attachments(body)
    assert [x["url"] for x in out] == [
        "https://files.linear.app/a.png",
        "https://files.linear.app/b.webp",
    ]
    assert all(x["sourceType"] == "image" for x in out)
