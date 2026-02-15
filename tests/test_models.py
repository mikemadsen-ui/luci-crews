"""
Unit tests for Pydantic models.
"""

import pytest
from pydantic import ValidationError
from luci_crews.models import (
    CrewResponse,
    SalesPipelineRequest,
    OpportunityDataModel,
    TranscriptionDataModel,
    OpportunityStrategyRequest,
    PresalesContextModel,
)


class TestCrewResponse:
    """Tests for CrewResponse model."""

    def test_success_response(self):
        """Create successful response."""
        response = CrewResponse(
            success=True,
            result={"analysis": "complete"},
            execution_time=1.5,
        )
        assert response.success is True
        assert response.result == {"analysis": "complete"}
        assert response.execution_time == 1.5
        assert response.error is None

    def test_error_response(self):
        """Create error response."""
        response = CrewResponse(
            success=False,
            error="Something went wrong",
        )
        assert response.success is False
        assert response.error == "Something went wrong"
        assert response.result is None

    def test_with_job_id(self):
        """Response with job ID for async operations."""
        response = CrewResponse(
            success=True,
            job_id="job-123-abc",
        )
        assert response.job_id == "job-123-abc"

    def test_required_fields(self):
        """success is required."""
        with pytest.raises(ValidationError):
            CrewResponse()


class TestSalesPipelineRequest:
    """Tests for SalesPipelineRequest model."""

    def test_valid_request(self):
        """Create valid sales pipeline request."""
        request = SalesPipelineRequest(
            user_id="user-123",
            user_email="user@example.com",
            opportunities=[{"name": "Deal 1"}],
        )
        assert request.user_id == "user-123"
        assert request.user_email == "user@example.com"
        assert len(request.opportunities) == 1

    def test_required_fields(self):
        """user_id and user_email are required."""
        with pytest.raises(ValidationError):
            SalesPipelineRequest()

    def test_optional_summary(self):
        """Summary is optional."""
        request = SalesPipelineRequest(
            user_id="user-123",
            user_email="user@example.com",
        )
        assert request.summary is None


class TestOpportunityDataModel:
    """Tests for OpportunityDataModel."""

    def test_all_fields_optional(self):
        """All fields are optional."""
        model = OpportunityDataModel()
        assert model.id is None
        assert model.name is None
        assert model.amount is None

    def test_full_data(self):
        """Create with full data."""
        model = OpportunityDataModel(
            id="opp-123",
            salesforce_id="00612345",
            name="Enterprise Deal",
            amount=50000.0,
            stage_name="Negotiation",
            probability=75,
            close_date="2025-03-31",
            owner_name="John Doe",
            owner_email="john@example.com",
            account_name="Acme Corp",
            account_tier="Enterprise",
        )
        assert model.name == "Enterprise Deal"
        assert model.amount == 50000.0
        assert model.probability == 75
        assert model.account_tier == "Enterprise"

    def test_serialization(self):
        """Model serializes to dict correctly."""
        model = OpportunityDataModel(name="Test", amount=1000)
        data = model.model_dump(exclude_none=True)
        assert data == {"name": "Test", "amount": 1000}


class TestTranscriptionDataModel:
    """Tests for TranscriptionDataModel."""

    def test_required_id(self):
        """id is required."""
        with pytest.raises(ValidationError):
            TranscriptionDataModel()

    def test_valid_transcription(self):
        """Create valid transcription data."""
        model = TranscriptionDataModel(
            id="trans-123",
            subject="Discovery Call",
            date="2025-02-01T10:00:00Z",
            text="Meeting transcript...",
            is_presales=True,
        )
        assert model.id == "trans-123"
        assert model.subject == "Discovery Call"
        assert model.is_presales is True

    def test_minimal_data(self):
        """Create with only required field."""
        model = TranscriptionDataModel(id="trans-456")
        assert model.id == "trans-456"
        assert model.subject is None
        assert model.is_presales is None


class TestPresalesContextModel:
    """Tests for PresalesContextModel."""

    def test_default_values(self):
        """Default values are set correctly."""
        model = PresalesContextModel()
        assert model.presalesCount == 0
        assert model.postsaleCount == 0
        assert model.isExistingCustomer is False

    def test_with_data(self):
        """Create with context data."""
        model = PresalesContextModel(
            presalesCount=5,
            postsaleCount=10,
            customerStartDate="2024-01-15",
            isExistingCustomer=True,
        )
        assert model.presalesCount == 5
        assert model.isExistingCustomer is True


class TestOpportunityStrategyRequest:
    """Tests for OpportunityStrategyRequest."""

    def test_required_opportunity_id(self):
        """opportunityId is required."""
        with pytest.raises(ValidationError):
            OpportunityStrategyRequest()

    def test_minimal_request(self):
        """Create with only required field."""
        request = OpportunityStrategyRequest(opportunityId="opp-123")
        assert request.opportunityId == "opp-123"
        assert request.forceRefresh is False

    def test_full_request(self):
        """Create with all fields."""
        request = OpportunityStrategyRequest(
            opportunityId="opp-123",
            userId="user-456",
            userEmail="user@example.com",
            forceRefresh=True,
            opportunityData=OpportunityDataModel(name="Big Deal"),
            transcriptionIds=["trans-1", "trans-2"],
            transcriptionData=[
                TranscriptionDataModel(id="trans-1", subject="Call 1"),
            ],
            salesforceAccountId="001ABC",
            presalesContext=PresalesContextModel(presalesCount=3),
        )
        assert request.opportunityId == "opp-123"
        assert request.forceRefresh is True
        assert request.opportunityData.name == "Big Deal"
        assert len(request.transcriptionIds) == 2
        assert request.presalesContext.presalesCount == 3
