"""
Feature Request Extraction Crew

Extracts and categorizes feature requests from customer transcript chunks.
Identifies product area, urgency, and business impact.
"""

import logging
from typing import Optional, List, Dict, Any
from crewai import Agent, Task, Crew, Process

from .base_crew import BaseCrew
from ..utils import extract_json_from_llm_response

logger = logging.getLogger(__name__)

# LeanData product categories
PRODUCT_CATEGORIES = [
    'matching',
    'routing',
    'bookit',
    'attribution',
    'revenue_intelligence',
    'engagement',
    'general',
]


class FeatureExtractionCrew(BaseCrew):
    """Crew for extracting feature requests from customer transcripts."""

    def _create_agents(self):
        """Create agents from configuration."""
        extractor_config = self._get_agent_config("feature_request_extractor")

        self.extractor = Agent(
            role=extractor_config.get("role", "Feature Request Analyst"),
            goal=extractor_config.get("goal", "Extract and categorize feature requests from customer conversations"),
            backstory=extractor_config.get("backstory", "Expert product analyst"),
            verbose=extractor_config.get("verbose", True),
            allow_delegation=extractor_config.get("allow_delegation", False),
            llm=self.llm,
        )

    def _format_transcript_chunks(self, chunks: List[Dict[str, Any]]) -> str:
        """Format transcript chunks for the task prompt."""
        if not chunks:
            return "No transcript data provided."

        formatted_parts = []
        for i, chunk in enumerate(chunks, 1):
            account = chunk.get('accountName', 'Unknown Account')
            subject = chunk.get('meetingSubject', 'Meeting')
            date = chunk.get('meetingDate', 'Unknown date')
            content = chunk.get('content', '')

            formatted_parts.append(
                f"--- Excerpt {i}: {account} - {subject} ({date}) ---\n{content}\n"
            )

        return "\n".join(formatted_parts)

    def _create_tasks(self, transcript_chunks: List[Dict[str, Any]]):
        """Create tasks from configuration with data interpolation."""
        task_config = self._get_task_config("extract_feature_requests")

        formatted_chunks = self._format_transcript_chunks(transcript_chunks)

        description = task_config.get("description", "").format(
            transcript_chunks=formatted_chunks,
        )

        self.extract_task = Task(
            description=description,
            expected_output=task_config.get("expected_output", "JSON array of feature requests"),
            agent=self.extractor,
        )

    def _parse_json_result(self, result_text: str) -> List[Dict[str, Any]]:
        """Parse JSON array from the crew result."""
        parsed = extract_json_from_llm_response(result_text, default={"items": []})
        # Handle array wrapped in items key
        if "items" in parsed and isinstance(parsed["items"], list):
            return parsed["items"]
        # Handle direct list (shouldn't happen with current utility but be safe)
        if isinstance(parsed, list):
            return parsed
        return []

    def _validate_and_clean_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and clean a feature request object."""
        # Required fields
        if not request.get('title'):
            return None

        # Validate and normalize product_category
        category = request.get('product_category', 'general').lower()
        if category not in PRODUCT_CATEGORIES:
            category = 'general'

        # Validate and normalize request_type
        valid_types = ['feature', 'enhancement', 'bug', 'integration', 'performance', 'usability']
        request_type = request.get('request_type', 'feature').lower()
        if request_type not in valid_types:
            request_type = 'feature'

        # Validate and normalize urgency
        valid_urgencies = ['low', 'medium', 'high', 'critical']
        urgency = request.get('urgency', 'medium').lower()
        if urgency not in valid_urgencies:
            urgency = 'medium'

        # Validate and normalize sentiment
        valid_sentiments = ['positive', 'neutral', 'negative', 'frustrated']
        sentiment = request.get('sentiment', 'neutral').lower()
        if sentiment not in valid_sentiments:
            sentiment = 'neutral'

        # Validate confidence score
        confidence = request.get('confidence_score')
        if confidence is not None:
            try:
                confidence = float(confidence)
                confidence = max(0.0, min(1.0, confidence))
            except (ValueError, TypeError):
                confidence = None

        return {
            'title': request.get('title'),
            'description': request.get('description'),
            'verbatim_quote': request.get('verbatim_quote'),
            'speaker_name': request.get('speaker_name'),
            'account_name': request.get('account_name'),
            'meeting_subject': request.get('meeting_subject'),
            'meeting_date': request.get('meeting_date'),
            'product_category': category,
            'request_type': request_type,
            'urgency': urgency,
            'sentiment': sentiment,
            'business_impact': request.get('business_impact'),
            'confidence_score': confidence,
        }

    def run(
        self,
        transcript_chunks: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Run the feature extraction crew.

        Args:
            transcript_chunks: List of transcript excerpts with metadata.
                Each chunk should have: content, accountName, meetingSubject, meetingDate

        Returns:
            Dict with 'feature_requests' list and 'count'
        """
        if not transcript_chunks:
            logger.warning("No transcript chunks provided")
            return {
                "feature_requests": [],
                "count": 0,
            }

        logger.info(f"[Feature Extraction] Processing {len(transcript_chunks)} transcript chunks")

        self._create_agents()
        self._create_tasks(transcript_chunks)

        crew = Crew(
            agents=[self.extractor],
            tasks=[self.extract_task],
            process=Process.sequential,
            verbose=False,
        )

        result = crew.kickoff()
        result_text = str(result)

        # Parse the JSON result
        raw_requests = self._parse_json_result(result_text)

        # Validate and clean each request
        feature_requests = []
        for raw_req in raw_requests:
            cleaned = self._validate_and_clean_request(raw_req)
            if cleaned:
                feature_requests.append(cleaned)

        logger.info(f"[Feature Extraction] Extracted {len(feature_requests)} valid feature requests")

        return {
            "feature_requests": feature_requests,
            "count": len(feature_requests),
        }
