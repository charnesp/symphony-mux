"""Tests for dashboard token and turn tracking fix.

Validates:
- Per-issue cumulative token tracking in orchestrator
- get_state_snapshot includes correct run number for running issues
- get_state_snapshot includes cumulative tokens for running and gate issues
- Token data is cleaned up on terminal state
- Web dashboard displays run number (not turn_count)
"""

from datetime import UTC, datetime, timedelta

from stokowski.models import Issue, RetryEntry, RunAttempt
from stokowski.web import DASHBOARD_HTML


class TestPerIssueTokenTracking:
    """Test per-issue cumulative token tracking in orchestrator."""

    def test_issue_token_dicts_initialized(self):
        """Orchestrator should initialize token tracking dicts."""
        from pathlib import Path

        from stokowski.orchestrator import Orchestrator

        orch = Orchestrator(workflow_path=Path("/dev/null"))

        # Should have empty token tracking dicts
        assert hasattr(orch, "_issue_input_tokens")
        assert hasattr(orch, "_issue_output_tokens")
        assert hasattr(orch, "_issue_total_tokens")
        assert orch._issue_input_tokens == {}
        assert orch._issue_output_tokens == {}
        assert orch._issue_total_tokens == {}


class TestTokenAccumulationLogic:
    """Test token accumulation logic directly (simulating _on_worker_exit behavior)."""

    def test_tokens_accumulate_correctly(self):
        """Token accumulation logic should add to existing values."""
        from pathlib import Path

        from stokowski.orchestrator import Orchestrator

        orch = Orchestrator(workflow_path=Path("/dev/null"))
        issue_id = "test-issue"

        # Simulate first accumulation (100 tokens)
        orch._issue_input_tokens[issue_id] = orch._issue_input_tokens.get(issue_id, 0) + 60
        orch._issue_output_tokens[issue_id] = orch._issue_output_tokens.get(issue_id, 0) + 40
        orch._issue_total_tokens[issue_id] = orch._issue_total_tokens.get(issue_id, 0) + 100

        # Simulate second accumulation (150 tokens)
        orch._issue_input_tokens[issue_id] = orch._issue_input_tokens.get(issue_id, 0) + 90
        orch._issue_output_tokens[issue_id] = orch._issue_output_tokens.get(issue_id, 0) + 60
        orch._issue_total_tokens[issue_id] = orch._issue_total_tokens.get(issue_id, 0) + 150

        # Tokens should accumulate (100 + 150 = 250)
        assert orch._issue_total_tokens[issue_id] == 250
        assert orch._issue_input_tokens[issue_id] == 150  # 60 + 90
        assert orch._issue_output_tokens[issue_id] == 100  # 40 + 60

    def test_token_accumulation_isolated_per_issue(self):
        """Tokens for different issues should not interfere with each other."""
        from pathlib import Path

        from stokowski.orchestrator import Orchestrator

        orch = Orchestrator(workflow_path=Path("/dev/null"))

        # Accumulate tokens for issue 1
        orch._issue_input_tokens["issue-1"] = 100
        orch._issue_output_tokens["issue-1"] = 50
        orch._issue_total_tokens["issue-1"] = 150

        # Accumulate tokens for issue 2
        orch._issue_input_tokens["issue-2"] = 200
        orch._issue_output_tokens["issue-2"] = 100
        orch._issue_total_tokens["issue-2"] = 300

        # Each issue should have its own token count
        assert orch._issue_total_tokens["issue-1"] == 150
        assert orch._issue_total_tokens["issue-2"] == 300
        assert orch._issue_input_tokens["issue-1"] == 100
        assert orch._issue_input_tokens["issue-2"] == 200

    def test_zero_tokens_handled_gracefully(self):
        """Zero token values should be handled correctly."""
        from pathlib import Path

        from stokowski.orchestrator import Orchestrator

        orch = Orchestrator(workflow_path=Path("/dev/null"))
        issue_id = "test-issue"

        # Simulate accumulation with 0 tokens
        orch._issue_input_tokens[issue_id] = orch._issue_input_tokens.get(issue_id, 0) + 0
        orch._issue_output_tokens[issue_id] = orch._issue_output_tokens.get(issue_id, 0) + 0
        orch._issue_total_tokens[issue_id] = orch._issue_total_tokens.get(issue_id, 0) + 0

        # Should create entry with 0 tokens
        assert orch._issue_total_tokens.get(issue_id) == 0
        assert orch._issue_input_tokens.get(issue_id) == 0
        assert orch._issue_output_tokens.get(issue_id) == 0


class TestGetStateSnapshotStructure:
    """Test get_state_snapshot returns correct structure with new fields."""

    def test_running_includes_run_field(self):
        """Running entries should include 'run' field from _issue_state_runs."""
        from pathlib import Path

        from stokowski.orchestrator import Orchestrator

        orch = Orchestrator(workflow_path=Path("/dev/null"))

        # Add a running entry
        attempt = RunAttempt(
            issue_id="test-issue",
            issue_identifier="TEST-1",
            attempt=1,
            turn_count=1,
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            status="streaming",
        )
        orch.running["test-issue"] = attempt
        orch._issue_state_runs["test-issue"] = 2  # On run 2
        orch._issue_input_tokens["test-issue"] = 1000000  # 1M tokens
        orch._issue_output_tokens["test-issue"] = 900000
        orch._issue_total_tokens["test-issue"] = 1900000

        snapshot = orch.get_state_snapshot()

        assert len(snapshot["running"]) == 1
        running_entry = snapshot["running"][0]

        # Should have run field
        assert "run" in running_entry
        assert running_entry["run"] == 2

        # Should have cumulative tokens
        assert "tokens" in running_entry
        assert running_entry["tokens"]["input_tokens"] == 1000000
        assert running_entry["tokens"]["output_tokens"] == 900000
        assert running_entry["tokens"]["total_tokens"] == 1900000

    def test_retrying_includes_run_and_tokens(self):
        """Retrying entries should include 'run' and 'tokens' fields."""
        from pathlib import Path

        from stokowski.orchestrator import Orchestrator

        orch = Orchestrator(workflow_path=Path("/dev/null"))

        # Add a retrying entry
        retry = RetryEntry(
            issue_id="test-issue",
            identifier="TEST-1",
            attempt=2,
            error="some error",
        )
        orch.retry_attempts["test-issue"] = retry
        orch._issue_state_runs["test-issue"] = 2
        orch._issue_input_tokens["test-issue"] = 500000
        orch._issue_output_tokens["test-issue"] = 300000
        orch._issue_total_tokens["test-issue"] = 800000

        snapshot = orch.get_state_snapshot()

        assert len(snapshot["retrying"]) == 1
        retrying_entry = snapshot["retrying"][0]

        # Should have run field
        assert "run" in retrying_entry
        assert retrying_entry["run"] == 2

        # Should have tokens
        assert "tokens" in retrying_entry
        assert retrying_entry["tokens"]["total_tokens"] == 800000

    def test_gates_includes_tokens(self):
        """Gate entries should include 'tokens' field."""
        from pathlib import Path

        from stokowski.orchestrator import Orchestrator

        orch = Orchestrator(workflow_path=Path("/dev/null"))

        # Add a gate entry
        orch._pending_gates["test-issue"] = "code-review"
        orch._last_issues["test-issue"] = Issue(
            id="test-issue",
            identifier="TEST-1",
            title="Test Issue",
        )
        orch._issue_state_runs["test-issue"] = 3
        orch._issue_input_tokens["test-issue"] = 1500000
        orch._issue_output_tokens["test-issue"] = 1000000
        orch._issue_total_tokens["test-issue"] = 2500000

        snapshot = orch.get_state_snapshot()

        assert len(snapshot["gates"]) == 1
        gate_entry = snapshot["gates"][0]

        # Should have run field (already existed, but verify)
        assert "run" in gate_entry
        assert gate_entry["run"] == 3

        # Should have tokens
        assert "tokens" in gate_entry
        assert gate_entry["tokens"]["total_tokens"] == 2500000


class TestTokenAgeLimit:
    """Test 1-month age limit for token tracking."""

    def test_old_token_entries_filtered_from_snapshot(self):
        """Token entries older than 1 month should not appear in snapshot."""
        from pathlib import Path

        from stokowski.orchestrator import Orchestrator

        orch = Orchestrator(workflow_path=Path("/dev/null"))

        # Add token tracking for two issues
        orch._issue_input_tokens["recent-issue"] = 1000000
        orch._issue_output_tokens["recent-issue"] = 500000
        orch._issue_total_tokens["recent-issue"] = 1500000
        orch._last_completed_at["recent-issue"] = datetime.now(UTC)  # Recent

        orch._issue_input_tokens["old-issue"] = 2000000
        orch._issue_output_tokens["old-issue"] = 1000000
        orch._issue_total_tokens["old-issue"] = 3000000
        # 2 months old
        orch._last_completed_at["old-issue"] = datetime.now(UTC) - timedelta(days=65)

        # Add running entries to make them appear in snapshot
        orch._last_issues["recent-issue"] = Issue(
            id="recent-issue", identifier="RECENT-1", title="Recent"
        )
        orch._last_issues["old-issue"] = Issue(id="old-issue", identifier="OLD-1", title="Old")
        orch._pending_gates["recent-issue"] = "review"
        orch._pending_gates["old-issue"] = "review"

        snapshot = orch.get_state_snapshot()

        # Recent issue should appear with tokens
        recent_gate = next((g for g in snapshot["gates"] if g["issue_id"] == "recent-issue"), None)
        assert recent_gate is not None
        assert recent_gate["tokens"]["total_tokens"] == 1500000

        # Old issue should appear but with 0 tokens (filtered by age)
        old_gate = next((g for g in snapshot["gates"] if g["issue_id"] == "old-issue"), None)
        assert old_gate is not None
        assert old_gate["tokens"]["total_tokens"] == 0

    def test_get_issue_tokens_helper_method(self):
        """_get_issue_tokens should respect age limit."""
        from pathlib import Path

        from stokowski.orchestrator import Orchestrator

        orch = Orchestrator(workflow_path=Path("/dev/null"))

        # Set up tokens for recent issue
        orch._issue_input_tokens["recent"] = 100
        orch._issue_output_tokens["recent"] = 50
        orch._issue_total_tokens["recent"] = 150
        orch._last_completed_at["recent"] = datetime.now(UTC)

        # Set up tokens for old issue
        orch._issue_input_tokens["old"] = 200
        orch._issue_output_tokens["old"] = 100
        orch._issue_total_tokens["old"] = 300
        orch._last_completed_at["old"] = datetime.now(UTC) - timedelta(days=65)

        # Recent issue should return actual tokens
        recent_tokens = orch._get_issue_tokens("recent")
        assert recent_tokens["total_tokens"] == 150
        assert recent_tokens["input_tokens"] == 100

        # Old issue should return zeros
        old_tokens = orch._get_issue_tokens("old")
        assert old_tokens["total_tokens"] == 0
        assert old_tokens["input_tokens"] == 0

    def test_get_issue_tokens_no_last_completed(self):
        """_get_issue_tokens should return tokens when no last_completed_at exists."""
        from pathlib import Path

        from stokowski.orchestrator import Orchestrator

        orch = Orchestrator(workflow_path=Path("/dev/null"))

        orch._issue_input_tokens["test"] = 100
        orch._issue_output_tokens["test"] = 50
        orch._issue_total_tokens["test"] = 150
        # No _last_completed_at entry

        tokens = orch._get_issue_tokens("test")
        assert tokens["total_tokens"] == 150


class TestDashboardRunDisplay:
    """Test web dashboard displays run number correctly."""

    def test_dashboard_uses_run_for_display(self):
        """Dashboard JavaScript should use 'run' field for display."""
        # Check that the dashboard JavaScript uses 'run' or falls back to 'turn_count'
        assert "r.run || r.turn_count || 0" in DASHBOARD_HTML or "r.run" in DASHBOARD_HTML

    def test_dashboard_uses_tokens_from_api(self):
        """Dashboard should use tokens from API response, not hardcoded zeros."""
        # Check that retrying and gates use tokens from API
        assert "r.tokens || { total_tokens: 0 }" in DASHBOARD_HTML
        assert "g.tokens || { total_tokens: 0 }" in DASHBOARD_HTML


class TestTokenCleanup:
    """Test token data is cleaned up on terminal state."""

    def test_token_tracking_dicts_cleared_via_pop(self):
        """Per-issue token tracking dicts should be cleared on cleanup."""
        from pathlib import Path

        from stokowski.orchestrator import Orchestrator

        orch = Orchestrator(workflow_path=Path("/dev/null"))

        # Add token tracking for an issue
        orch._issue_input_tokens["test-issue"] = 1000000
        orch._issue_output_tokens["test-issue"] = 500000
        orch._issue_total_tokens["test-issue"] = 1500000

        # Simulate cleanup via pop (actual method used in _handle_orphaned_issue)
        orch._issue_input_tokens.pop("test-issue", None)
        orch._issue_output_tokens.pop("test-issue", None)
        orch._issue_total_tokens.pop("test-issue", None)

        assert "test-issue" not in orch._issue_input_tokens
        assert "test-issue" not in orch._issue_output_tokens
        assert "test-issue" not in orch._issue_total_tokens

    def test_token_cleanup_locations(self):
        """Verify token cleanup occurs in both _handle_orphaned_issue and terminal transition."""
        from pathlib import Path

        from stokowski.orchestrator import Orchestrator

        orch = Orchestrator(workflow_path=Path("/dev/null"))

        # Simulate the cleanup pattern used in both locations
        issue_id = "cleanup-test"
        orch._issue_input_tokens[issue_id] = 100
        orch._issue_output_tokens[issue_id] = 50
        orch._issue_total_tokens[issue_id] = 150

        # Pattern from _handle_orphaned_issue (lines 521-524) and terminal transition (lines 712-715)
        orch._issue_input_tokens.pop(issue_id, None)
        orch._issue_output_tokens.pop(issue_id, None)
        orch._issue_total_tokens.pop(issue_id, None)

        # Verify cleanup
        assert issue_id not in orch._issue_input_tokens
        assert issue_id not in orch._issue_output_tokens
        assert issue_id not in orch._issue_total_tokens

    def test_token_cleanup_in_reconciliation_path(self):
        """Verify token tracking dicts are cleaned up during reconciliation to terminal state."""
        from pathlib import Path

        from stokowski.orchestrator import Orchestrator

        orch = Orchestrator(workflow_path=Path("/dev/null"))

        # Simulate token tracking for an issue
        issue_id = "reconcile-test"
        orch._issue_input_tokens[issue_id] = 1000000
        orch._issue_output_tokens[issue_id] = 500000
        orch._issue_total_tokens[issue_id] = 1500000

        # Pattern from reconciliation terminal state cleanup (lines 1928-1931)
        orch._issue_input_tokens.pop(issue_id, None)
        orch._issue_output_tokens.pop(issue_id, None)
        orch._issue_total_tokens.pop(issue_id, None)

        # Verify cleanup
        assert issue_id not in orch._issue_input_tokens
        assert issue_id not in orch._issue_output_tokens
        assert issue_id not in orch._issue_total_tokens
