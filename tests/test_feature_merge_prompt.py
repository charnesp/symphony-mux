"""Merge stage prompt: OpenSpec archive is ordered before PR merge instructions."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MERGE_MD = REPO_ROOT / "prompts" / "feature" / "merge.md"


def test_merge_prompt_openspec_section_before_merge_steps():
    text = MERGE_MD.read_text()
    assert text.index("## OpenSpec") < text.index("## Merge Steps")


def test_merge_prompt_execution_order_requires_archive_before_gh_merge():
    text = MERGE_MD.read_text()
    assert "OpenSpec archive" in text
    assert "**before** any `gh pr merge`" in text


def test_merge_prompt_does_not_defer_openspec_until_after_merge():
    text = MERGE_MD.read_text()
    assert "After the PR/MR is **successfully merged**" not in text
