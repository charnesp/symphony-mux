"""Tests for prompt assembly module."""

import pytest
from stokowski.config import StateConfig, LinearStatesConfig
from stokowski.models import Issue
from stokowski.prompt import build_lifecycle_section


def test_lifecycle_accepts_workflow_states_parameter():
    """Verify build_lifecycle_section accepts workflow_states parameter."""
    issue = Issue(
        id="test-123",
        identifier="PROJ-1",
        title="Test issue",
        state="In Progress",
    )
    
    state_cfg = StateConfig(
        name="implement",
        type="agent",
        transitions={"complete": "review"},
    )
    
    workflow_states = {
        "implement": {"type": "agent"},
        "review": {"type": "gate"},
    }
    
    # Should not raise TypeError - parameter is accepted
    result = build_lifecycle_section(
        issue=issue,
        state_name="implement",
        state_cfg=state_cfg,
        linear_states=LinearStatesConfig(),
        workflow_states=workflow_states,
    )
    
    # Basic check that we got a string result
    assert isinstance(result, str)
    assert "Lifecycle Context" in result

def test_lifecycle_includes_gate_section_when_next_is_gate():
    """When next state is a gate, include approval instructions."""
    issue = Issue(
        id="test-123",
        identifier="PROJ-1",
        title="Test issue",
        state="In Progress",
    )
    
    state_cfg = StateConfig(
        name="implement",
        type="agent",
        transitions={"complete": "review"},
    )
    
    # Use StateConfig objects (not dicts) to match real usage
    workflow_states = {
        "implement": StateConfig(name="implement", type="agent"),
        "review": StateConfig(name="review", type="gate"),
    }
    
    result = build_lifecycle_section(
        issue=issue,
        state_name="implement",
        state_cfg=state_cfg,
        linear_states=LinearStatesConfig(),
        workflow_states=workflow_states,
    )
    
    # Should contain gate-specific instructions
    assert "Gate Review Required" in result
    assert "Approval Required" in result
    assert "stokowski:report" in result

