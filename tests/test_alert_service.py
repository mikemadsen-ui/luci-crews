"""Tests for alert service."""
import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, patch
from src.luci_crews.alert_service import should_alert, create_alert, trigger_email


def test_should_alert_returns_false_for_low_priority():
    """LOW priority tasks should never alert."""
    supabase = Mock()

    result = should_alert(
        alert_type="billing_failure",
        crew_type="test_crew",
        task_priority="LOW",
        supabase=supabase
    )

    assert result is False
    supabase.table.assert_not_called()


def test_should_alert_returns_false_for_duplicate_in_24h():
    """Same alert within 24h should be skipped."""
    # Mock Supabase to return existing alert
    supabase = Mock()
    supabase.table.return_value.select.return_value.eq.return_value.gte.return_value.limit.return_value.execute.return_value.data = [{"id": "123"}]

    result = should_alert(
        alert_type="billing_failure",
        crew_type="test_crew",
        task_priority="MEDIUM",
        supabase=supabase
    )

    assert result is False


def test_should_alert_returns_true_for_new_alert():
    """New alert should be allowed."""
    # Mock Supabase to return no existing alerts
    supabase = Mock()
    supabase.table.return_value.select.return_value.eq.return_value.gte.return_value.limit.return_value.execute.return_value.data = []

    result = should_alert(
        alert_type="billing_failure",
        crew_type="test_crew",
        task_priority="MEDIUM",
        supabase=supabase
    )

    assert result is True


def test_create_alert_returns_none_when_should_not_alert():
    """Alert creation should be skipped if dedup check fails."""
    supabase = Mock()
    # Mock existing alert (should_alert returns False)
    supabase.table.return_value.select.return_value.eq.return_value.gte.return_value.limit.return_value.execute.return_value.data = [{"id": "123"}]

    result = create_alert(
        alert_type="billing_failure",
        crew_type="test_crew",
        task_name="test_task",
        task_priority="MEDIUM",
        user_id="user123",
        providers_tried=["openai/gpt-4.1"],
        exhausted_providers=["anthropic"],
        error_message="Test error",
        supabase=supabase
    )

    assert result is None


def test_create_alert_inserts_and_returns_id():
    """Successful alert creation returns alert ID."""
    supabase = Mock()
    # No existing alert
    supabase.table.return_value.select.return_value.eq.return_value.gte.return_value.limit.return_value.execute.return_value.data = []
    # Mock insert result
    supabase.table.return_value.insert.return_value.execute.return_value.data = [{"id": "alert-id-123"}]

    result = create_alert(
        alert_type="billing_failure",
        crew_type="test_crew",
        task_name="test_task",
        task_priority="MEDIUM",
        user_id="user123",
        providers_tried=["openai/gpt-4.1", "anthropic/claude-sonnet-4-6"],
        exhausted_providers=["anthropic"],
        error_message="Test error message",
        supabase=supabase
    )

    assert result == "alert-id-123"
    # Verify insert was called
    supabase.table.return_value.insert.assert_called_once()


@patch('src.luci_crews.alert_service.requests.post')
def test_trigger_email_calls_worker_endpoint(mock_post):
    """trigger_email should POST to luci-worker endpoint."""
    mock_post.return_value.ok = True

    trigger_email("alert-id-123")

    # Verify POST was called with correct URL and payload
    mock_post.assert_called_once()
    call_args = mock_post.call_args
    assert "alert_id" in call_args.kwargs['json']
    assert call_args.kwargs['json']['alert_id'] == "alert-id-123"
    assert call_args.kwargs['timeout'] == 5


@patch('src.luci_crews.alert_service.requests.post')
def test_trigger_email_handles_failure_gracefully(mock_post):
    """Email trigger failures should not raise exceptions."""
    mock_post.side_effect = Exception("Connection failed")

    # Should not raise
    trigger_email("alert-id-123")
