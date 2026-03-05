"""Tests for alert service."""
import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock
from src.luci_crews.alert_service import should_alert


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
