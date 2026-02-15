"""
Call Analysis Crew

Performs per-call sentiment and engagement analysis on meeting transcripts.
Analyzes customer sentiment toward product, company, and IC, plus engagement metrics.
"""

import os
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from crewai import Agent, Task, Crew, Process

from .base_crew import BaseCrew
from ..utils import extract_json_from_llm_response

logger = logging.getLogger(__name__)

# Vendor domains for speaker classification
VENDOR_DOMAINS = ['leandata.com', 'leandatainc.com']


class CallAnalysisCrew(BaseCrew):
    """Crew for analyzing individual call transcripts."""

    def _create_agents(self):
        """Create the analysis agents."""
        # Sentiment Analyzer - analyzes customer feelings toward product/company/IC
        sentiment_config = self._get_agent_config("call_sentiment_analyzer")
        self.sentiment_analyzer = Agent(
            role=sentiment_config.get("role", "Customer Sentiment Analyst"),
            goal=sentiment_config.get("goal", "Analyze customer sentiment from call transcripts"),
            backstory=sentiment_config.get("backstory", "Expert at detecting emotional undertones in conversations"),
            verbose=sentiment_config.get("verbose", True),
            allow_delegation=False,
            llm=self.llm,
        )

        # Engagement Analyzer - analyzes talk patterns and participation
        engagement_config = self._get_agent_config("call_engagement_analyzer")
        self.engagement_analyzer = Agent(
            role=engagement_config.get("role", "Meeting Engagement Analyst"),
            goal=engagement_config.get("goal", "Analyze meeting dynamics and engagement patterns"),
            backstory=engagement_config.get("backstory", "Expert at analyzing conversation dynamics"),
            verbose=engagement_config.get("verbose", True),
            allow_delegation=False,
            llm=self.llm,
        )

        # Action Item Extractor - extracts commitments, blockers, decisions
        action_config = self._get_agent_config("call_action_extractor")
        self.action_extractor = Agent(
            role=action_config.get("role", "Action Item Extractor"),
            goal=action_config.get("goal", "Extract commitments, blockers, and decisions from calls"),
            backstory=action_config.get("backstory", "Expert at identifying actionable items in conversations"),
            verbose=action_config.get("verbose", True),
            allow_delegation=False,
            llm=self.llm,
        )

        # Risk Assessor - synthesizes findings into risk assessment
        risk_config = self._get_agent_config("call_risk_assessor")
        self.risk_assessor = Agent(
            role=risk_config.get("role", "Implementation Risk Assessor"),
            goal=risk_config.get("goal", "Assess implementation risk and provide coaching"),
            backstory=risk_config.get("backstory", "Expert at identifying project risks from customer interactions"),
            verbose=risk_config.get("verbose", True),
            allow_delegation=False,
            llm=self.llm,
        )

    def _classify_speakers(
        self,
        speakers: List[Dict],
        attendees: Optional[List[Dict]] = None
    ) -> Dict[str, str]:
        """
        Classify speakers as vendor or customer based on email domain.

        Args:
            speakers: List of speaker objects from transcript
            attendees: Optional list of meeting attendees with emails

        Returns:
            Dict mapping speaker_id/name to 'vendor' or 'customer'
        """
        classification = {}
        attendee_map = {}

        # Build attendee lookup by name (case-insensitive)
        if attendees:
            for att in attendees:
                name = (att.get("name") or "").lower()
                email = att.get("email") or ""
                if name and email:
                    attendee_map[name] = email

        for speaker in speakers:
            # Use ID if available, otherwise fall back to name as key
            speaker_id = speaker.get("id") or speaker.get("speaker_id")
            speaker_name = speaker.get("name") or ""
            speaker_email = speaker.get("email") or ""

            # Use name as the key if no ID (common in simpler formats)
            key = str(speaker_id) if speaker_id else speaker_name
            if not key:
                continue

            speaker_name_lower = speaker_name.lower()

            # First check if speaker has email directly
            if speaker_email:
                domain = speaker_email.split("@")[-1].lower()
                speaker_type = "vendor" if domain in VENDOR_DOMAINS else "customer"
                classification[key] = speaker_type
                # Also store by name for fallback lookups
                if speaker_name:
                    classification[speaker_name] = speaker_type
                continue

            # Try to match speaker to attendee by name
            matched_email = None
            for att_name, att_email in attendee_map.items():
                # Check if speaker name contains attendee name or vice versa
                if att_name in speaker_name_lower or speaker_name_lower in att_name:
                    matched_email = att_email
                    break

            if matched_email:
                domain = matched_email.split("@")[-1].lower()
                speaker_type = "vendor" if domain in VENDOR_DOMAINS else "customer"
                classification[key] = speaker_type
                if speaker_name:
                    classification[speaker_name] = speaker_type
            else:
                # Default: assume customer if can't match (safer assumption)
                # Unless name contains obvious vendor indicators
                if any(x in speaker_name_lower for x in ["leandata", "ld ", "consultant"]):
                    classification[key] = "vendor"
                    if speaker_name:
                        classification[speaker_name] = "vendor"
                else:
                    classification[key] = "customer"
                    if speaker_name:
                        classification[speaker_name] = "customer"

        return classification

    def _calculate_talk_time(
        self,
        segments: List[Dict],
        speaker_classification: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        Calculate talk time percentages from transcript segments.

        Args:
            segments: List of transcript segments with speaker_id and text
            speaker_classification: Dict mapping speaker_id to vendor/customer

        Returns:
            Dict with customer_pct, vendor_pct, and per-speaker breakdown
        """
        # Count words per speaker type (approximation of talk time)
        customer_words = 0
        vendor_words = 0
        speaker_words = {}

        for segment in segments:
            speaker_id = str(segment.get("speaker_id", segment.get("speaker", "")))
            text = segment.get("transcript", segment.get("text", ""))
            word_count = len(text.split())

            # Track per-speaker
            if speaker_id not in speaker_words:
                speaker_words[speaker_id] = 0
            speaker_words[speaker_id] += word_count

            # Aggregate by type
            speaker_type = speaker_classification.get(speaker_id, "customer")
            if speaker_type == "vendor":
                vendor_words += word_count
            else:
                customer_words += word_count

        total_words = customer_words + vendor_words
        if total_words == 0:
            return {
                "customer_pct": 50.0,
                "vendor_pct": 50.0,
                "speaker_breakdown": {}
            }

        return {
            "customer_pct": round((customer_words / total_words) * 100, 2),
            "vendor_pct": round((vendor_words / total_words) * 100, 2),
            "speaker_breakdown": {
                sid: {
                    "words": words,
                    "pct": round((words / total_words) * 100, 2),
                    "type": speaker_classification.get(sid, "customer")
                }
                for sid, words in speaker_words.items()
            }
        }

    def _count_questions(
        self,
        segments: List[Dict],
        speaker_classification: Dict[str, str]
    ) -> Dict[str, int]:
        """Count questions asked by each speaker type."""
        customer_questions = 0
        vendor_questions = 0

        for segment in segments:
            speaker_id = str(segment.get("speaker_id", segment.get("speaker", "")))
            text = segment.get("transcript", segment.get("text", ""))

            # Simple question detection: count sentences ending with ?
            question_count = text.count("?")

            speaker_type = speaker_classification.get(speaker_id, "customer")
            if speaker_type == "vendor":
                vendor_questions += question_count
            else:
                customer_questions += question_count

        return {
            "customer": customer_questions,
            "vendor": vendor_questions
        }

    def _format_context(
        self,
        project_name: str,
        account_name: str,
        meeting_subject: str,
        meeting_date: str,
        implementation_stage: Optional[str],
        project_context: Optional[Dict]
    ) -> str:
        """Format context for analysis."""
        context = f"""=== CALL CONTEXT ===
Project: {project_name}
Account: {account_name}
Meeting: {meeting_subject}
Date: {meeting_date}
"""
        if implementation_stage:
            context += f"Implementation Stage: {implementation_stage}\n"

        if project_context:
            if project_context.get("target_go_live"):
                context += f"Target Go-Live: {project_context['target_go_live']}\n"
            if project_context.get("completion_pct"):
                context += f"Completion: {project_context['completion_pct']}%\n"
            if project_context.get("days_since_start"):
                context += f"Days Since Start: {project_context['days_since_start']}\n"

        return context

    def _format_transcript_with_speakers(
        self,
        segments: List[Dict],
        speakers: List[Dict],
        speaker_classification: Dict[str, str]
    ) -> str:
        """Format transcript with speaker names and types."""
        # Build speaker name map
        speaker_names = {}
        for speaker in speakers:
            sid = str(speaker.get("id", speaker.get("speaker_id", "")))
            name = speaker.get("name", f"Speaker {sid}")
            stype = speaker_classification.get(sid, "customer")
            speaker_names[sid] = f"{name} [{stype.upper()}]"

        lines = ["=== TRANSCRIPT ===\n"]
        for segment in segments:
            speaker_id = str(segment.get("speaker_id", segment.get("speaker", "")))
            speaker_label = speaker_names.get(speaker_id, f"Speaker {speaker_id}")
            text = segment.get("transcript", segment.get("text", ""))
            lines.append(f"{speaker_label}: {text}\n")

        return "\n".join(lines)

    def _create_tasks(
        self,
        context: str,
        transcript: str,
        talk_time: Dict,
        questions: Dict
    ) -> List[Task]:
        """Create the analysis tasks."""
        tasks = []

        # Task 1: Sentiment Analysis
        sentiment_task_config = self._get_task_config("analyze_call_sentiment")
        sentiment_description = sentiment_task_config.get("description", "").format(
            context=context,
            transcript=transcript
        ) if sentiment_task_config.get("description") else f"""
Analyze the customer sentiment in this call transcript.

{context}

{transcript}

Evaluate customer sentiment across THREE dimensions:
1. PRODUCT SENTIMENT: How does the customer feel about the LeanData product?
   - Are they excited, frustrated, confused, satisfied?
   - Do they see value? Express concerns about functionality?

2. COMPANY SENTIMENT: How does the customer feel about LeanData as a company?
   - Do they trust the company? Feel supported?
   - Any concerns about partnership, pricing, future?

3. IC SENTIMENT: How does the customer feel about the Implementation Consultant?
   - Do they feel heard, supported, confident in the IC?
   - Any frustration with communication, responsiveness?

For each dimension, provide:
- Score from -1.0 (very negative) to 1.0 (very positive), 0 = neutral
- Key quotes that support your assessment
- Specific signals you detected

Return as JSON:
{{
  "product_sentiment": {{
    "score": <-1.0 to 1.0>,
    "signals": ["<signal1>", "<signal2>"],
    "key_quotes": ["<quote1>", "<quote2>"]
  }},
  "company_sentiment": {{
    "score": <-1.0 to 1.0>,
    "signals": ["<signal1>"],
    "key_quotes": ["<quote1>"]
  }},
  "ic_sentiment": {{
    "score": <-1.0 to 1.0>,
    "signals": ["<signal1>"],
    "key_quotes": ["<quote1>"]
  }},
  "overall_sentiment": <-1.0 to 1.0>,
  "sentiment_summary": "<2-3 sentence summary>"
}}
"""
        tasks.append(Task(
            description=sentiment_description,
            expected_output=sentiment_task_config.get("expected_output", "JSON sentiment analysis"),
            agent=self.sentiment_analyzer,
        ))

        # Task 2: Engagement Analysis
        engagement_task_config = self._get_task_config("analyze_call_engagement")
        engagement_description = f"""
Analyze the engagement dynamics of this call.

{context}

CALCULATED METRICS:
- Customer Talk Time: {talk_time['customer_pct']}%
- Vendor Talk Time: {talk_time['vendor_pct']}%
- Customer Questions Asked: {questions['customer']}
- Vendor Questions Asked: {questions['vendor']}

{transcript}

Based on the transcript and metrics, assess:
1. ENGAGEMENT LEVEL: low, medium, or high
   - Low: Customer is disengaged, giving short answers, not asking questions
   - Medium: Normal participation, some questions, adequate responses
   - High: Active participation, many questions, detailed responses, enthusiasm

2. PARTICIPATION PATTERNS:
   - Is the customer actively contributing or passive?
   - Are they asking clarifying questions (good) or confused questions (concern)?
   - Do they volunteer information or need prompting?

3. CONVERSATION QUALITY:
   - Is this a productive conversation?
   - Are decisions being made?
   - Is there good back-and-forth or one-sided?

Return as JSON:
{{
  "engagement_level": "low" | "medium" | "high",
  "engagement_signals": ["<signal1>", "<signal2>"],
  "participation_assessment": "<1-2 sentence assessment>",
  "conversation_quality": "poor" | "adequate" | "good" | "excellent",
  "notable_patterns": ["<pattern1>", "<pattern2>"]
}}
"""
        tasks.append(Task(
            description=engagement_description,
            expected_output=engagement_task_config.get("expected_output", "JSON engagement analysis"),
            agent=self.engagement_analyzer,
        ))

        # Task 3: Action Item Extraction
        action_task_config = self._get_task_config("extract_call_actions")
        action_description = f"""
Extract all actionable items from this call transcript.

{context}

{transcript}

Identify and extract:

1. COMMITMENTS MADE:
   - Who committed to do what?
   - Is there a due date mentioned?
   - Classify owner as 'customer' or 'vendor'

2. BLOCKERS SURFACED:
   - What obstacles or blockers were mentioned?
   - How severe are they? (low/medium/high/critical)
   - Who owns resolving them?

3. DECISIONS MADE:
   - What decisions were reached?
   - Who made them?
   - What's the impact?

4. KEY CONCERNS RAISED:
   - What concerns did the customer express?
   - How severe? (low/medium/high)
   - Include direct quote if possible

5. POSITIVE SIGNALS:
   - What positive things did the customer say?
   - Signs of satisfaction, excitement, confidence?

Return as JSON:
{{
  "commitments_made": [
    {{"commitment": "<what>", "owner": "<name>", "owner_type": "customer" | "vendor", "due_date": "<date or null>"}}
  ],
  "blockers_surfaced": [
    {{"blocker": "<what>", "severity": "low" | "medium" | "high" | "critical", "owner": "<name or null>"}}
  ],
  "decision_points": [
    {{"decision": "<what>", "decided_by": "<who>", "impact": "<description>"}}
  ],
  "key_concerns": [
    {{"concern": "<what>", "severity": "low" | "medium" | "high", "quote": "<direct quote>"}}
  ],
  "positive_signals": [
    {{"signal": "<what>", "quote": "<direct quote>"}}
  ]
}}
"""
        tasks.append(Task(
            description=action_description,
            expected_output=action_task_config.get("expected_output", "JSON action items"),
            agent=self.action_extractor,
        ))

        # Task 4: Risk Assessment & Coaching
        risk_task_config = self._get_task_config("assess_call_risk")
        risk_description = f"""
Based on the previous analyses, assess the implementation risk and provide coaching.

{context}

Review the sentiment analysis, engagement analysis, and extracted action items from previous tasks.

Synthesize into:

1. RISK LEVEL: low, medium, high, or critical
   - Low: Customer is engaged, positive sentiment, no major concerns
   - Medium: Some concerns but manageable, neutral sentiment
   - High: Multiple concerns, negative sentiment trends, blockers
   - Critical: Serious issues, very negative sentiment, project at risk

2. RISK FACTORS: List specific risk factors identified

3. IMPLEMENTATION STAGE ASSESSMENT:
   Based on conversation content, which stage is this project likely in?
   - discovery: Understanding requirements, initial meetings
   - configuration: Setting up the product
   - testing: UAT, validation
   - training: User training, enablement
   - go-live: Launch preparation or just launched
   - post-go-live: Post-launch support

4. IC COACHING:
   - What should the IC do differently?
   - What follow-up actions are recommended?
   - How can they improve the customer relationship?

Return as JSON:
{{
  "risk_level": "low" | "medium" | "high" | "critical",
  "risk_factors": [
    {{"factor": "<description>", "severity": "low" | "medium" | "high"}}
  ],
  "implementation_stage": "<stage>",
  "coaching_notes": "<2-3 paragraphs of coaching advice>",
  "follow_up_actions": [
    {{"action": "<what>", "priority": "low" | "medium" | "high", "suggested_owner": "IC" | "customer" | "escalate"}}
  ]
}}
"""
        tasks.append(Task(
            description=risk_description,
            expected_output=risk_task_config.get("expected_output", "JSON risk assessment"),
            agent=self.risk_assessor,
        ))

        return tasks

    def _parse_json_result(self, raw_result: str) -> Dict[str, Any]:
        """Parse JSON from crew result."""
        return extract_json_from_llm_response(raw_result, default={"raw_text": raw_result})

    def run(
        self,
        transcript_segments: List[Dict],
        speakers: List[Dict],
        project_name: str,
        account_name: str,
        meeting_subject: str,
        meeting_date: str,
        attendees: Optional[List[Dict]] = None,
        implementation_stage: Optional[str] = None,
        project_context: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Run the call analysis crew.

        Args:
            transcript_segments: List of transcript segments with speaker_id and text
            speakers: List of speaker objects from Avoma
            project_name: Implementation project name
            account_name: Customer account name
            meeting_subject: Meeting title/subject
            meeting_date: ISO date string
            attendees: Optional list of meeting attendees with emails
            implementation_stage: Optional known implementation stage
            project_context: Optional dict with target_go_live, completion_pct, etc.

        Returns:
            Dict with full analysis results
        """
        start_time = datetime.utcnow()

        # Create agents
        self._create_agents()

        # Classify speakers
        speaker_classification = self._classify_speakers(speakers, attendees)
        logger.info(f"Speaker classification: {speaker_classification}")

        # Calculate engagement metrics
        talk_time = self._calculate_talk_time(transcript_segments, speaker_classification)
        questions = self._count_questions(transcript_segments, speaker_classification)
        logger.info(f"Talk time: customer={talk_time['customer_pct']}%, vendor={talk_time['vendor_pct']}%")
        logger.info(f"Questions: customer={questions['customer']}, vendor={questions['vendor']}")

        # Format inputs
        context = self._format_context(
            project_name, account_name, meeting_subject, meeting_date,
            implementation_stage, project_context
        )
        transcript = self._format_transcript_with_speakers(
            transcript_segments, speakers, speaker_classification
        )

        # Create tasks
        tasks = self._create_tasks(context, transcript, talk_time, questions)

        # Run crew
        crew = Crew(
            name="Call Analysis Crew",
            agents=[self.sentiment_analyzer, self.engagement_analyzer,
                    self.action_extractor, self.risk_assessor],
            tasks=tasks,
            process=Process.sequential,
            verbose=False,
        )

        result = crew.kickoff()

        # Parse results from each task
        task_outputs = []
        for task in tasks:
            if hasattr(task, 'output') and task.output:
                task_outputs.append(self._parse_json_result(str(task.output)))

        # Merge all outputs
        merged = {}
        for output in task_outputs:
            if isinstance(output, dict) and "raw_text" not in output:
                merged.update(output)

        # Build final result
        end_time = datetime.utcnow()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        # Extract sentiment scores
        product_sentiment = merged.get("product_sentiment", {})
        company_sentiment = merged.get("company_sentiment", {})
        ic_sentiment = merged.get("ic_sentiment", {})

        return {
            # Sentiment scores
            "product_sentiment": product_sentiment.get("score") if isinstance(product_sentiment, dict) else None,
            "company_sentiment": company_sentiment.get("score") if isinstance(company_sentiment, dict) else None,
            "ic_sentiment": ic_sentiment.get("score") if isinstance(ic_sentiment, dict) else None,
            "overall_sentiment": merged.get("overall_sentiment"),
            "sentiment_summary": merged.get("sentiment_summary"),

            # Engagement metrics
            "customer_talk_time_pct": talk_time["customer_pct"],
            "vendor_talk_time_pct": talk_time["vendor_pct"],
            "customer_questions_count": questions["customer"],
            "vendor_questions_count": questions["vendor"],
            "engagement_level": merged.get("engagement_level"),
            "engagement_signals": merged.get("engagement_signals", []),

            # Speakers with classification
            "speakers": [
                {
                    "id": str(s.get("id", s.get("speaker_id", ""))),
                    "name": s.get("name", "Unknown"),
                    "type": (
                        speaker_classification.get(str(s.get("id") or s.get("speaker_id") or ""))
                        or speaker_classification.get(s.get("name", ""))
                        or "customer"
                    ),
                    **(
                        talk_time["speaker_breakdown"].get(str(s.get("id") or s.get("speaker_id") or ""))
                        or talk_time["speaker_breakdown"].get(s.get("name", ""))
                        or {}
                    )
                }
                for s in speakers
            ],

            # Extracted insights
            "key_concerns": merged.get("key_concerns", []),
            "positive_signals": merged.get("positive_signals", []),
            "commitments_made": merged.get("commitments_made", []),
            "blockers_surfaced": merged.get("blockers_surfaced", []),
            "decision_points": merged.get("decision_points", []),

            # Risk assessment
            "implementation_stage": merged.get("implementation_stage", implementation_stage),
            "risk_level": merged.get("risk_level"),
            "risk_factors": merged.get("risk_factors", []),

            # Coaching
            "coaching_notes": merged.get("coaching_notes"),
            "follow_up_actions": merged.get("follow_up_actions", []),

            # Metadata
            "analyzed_at": end_time.isoformat(),
            "analysis_duration_ms": duration_ms,
            "model_version": "call_analysis_v1",

            # Raw outputs for debugging
            "_raw_outputs": task_outputs if os.environ.get("DEBUG") else None,
        }
