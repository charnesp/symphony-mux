"""Investigation prompts must require a local feature branch early (no push / no PR yet)."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INVESTIGATE_PROMPTS = [
    REPO_ROOT / "prompts" / "feature" / "investigate.md",
    REPO_ROOT / ".stokowski" / "prompts" / "feature" / "investigate.md",
]


def test_investigate_prompts_define_local_git_branch_early() -> None:
    for path in INVESTIGATE_PROMPTS:
        text = path.read_text(encoding="utf-8")
        assert path.is_file(), f"missing {path}"
        assert "## Local git" in text, f"{path} should document local git / branch setup"
        assert "git checkout -b" in text, f"{path} should instruct branch creation"
        assert "feature/" in text, f"{path} should mention feature/ naming"
        assert "fix/" in text, f"{path} should mention fix/ naming"
        assert "no push" in text.lower() or "do not" in text.lower(), f"{path} should forbid push"
        assert "pr" in text.lower(), f"{path} should mention PR/MR policy"
        assert "Create branches or PRs" not in text, (
            f"{path} must not blanket-forbid branch creation; forbid push/PR only"
        )


def test_stokowski_global_prompt_clarifies_branch_on_rework() -> None:
    path = REPO_ROOT / ".stokowski" / "prompts" / "global.md"
    text = path.read_text(encoding="utf-8")
    assert "rework" in text.lower(), path
    assert "feature branch" in text.lower(), path
    assert "first run" in text.lower() or "already exists" in text.lower(), (
        f"{path} should distinguish first run vs rework for branches"
    )
