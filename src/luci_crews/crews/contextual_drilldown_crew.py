"""
Contextual Drilldown Crew

Generates instant AI synthesis for a specific account or metric when an
executive clicks to drill down. Prioritizes speed (< 5 second response)
over depth, focusing on 'why is this flagged' context.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from crewai import Agent, Task, Crew, Process

from .base_crew import BaseCrew

logger = logging.getLogger(__name__)

# Valid entity types
ENTITY_TYPES = {"account", "metric", "renewal"}

# Valid context types
CONTEXT_TYPES = {"risk", "renewal", "expansion", "engagement"}


class ContextualDrilldownCrew(BaseCrew):
    """Crew for generating instant drilldown synthesis."""

    needs_supabase = True

    # ─── Data fetching ───────────────────────────────────────────────

    def _fetch_account_data(self, account_id: str) -> Dict[str, Any]:
        """Fetch account details."""
        if not self.supabase:
            return {}
        try:
            # Try by UUID first, then by salesforce_id
            result = self.supabase.table("accounts").select(
                "id, name, salesforce_id, contract_value, health_score, account_tier, "
                "industry, contract_end_date, days_since_last_touch, owner_name, "
                "utilization_pct"
            ).eq("id", account_id).limit(1).execute()

            if not result.data:
                result = self.supabase.table("accounts").select(
                    "id, name, salesforce_id, contract_value, health_score, account_tier, "
                    "industry, contract_end_date, days_since_last_touch, owner_name, "
                    "utilization_pct"
                ).eq("salesforce_id", account_id).limit(1).execute()

            return result.data[0] if result.data else {}
        except Exception as e:
            logger.error(f"Error fetching account data: {e}")
            return {}

    def _fetch_recent_analysis(self, account_id: str) -> List[Dict[str, Any]]:
        """Fetch recent crew analysis history for the account."""
        if not self.supabase:
            return []
        try:
            result = self.supabase.table("crew_analysis_history").select(
                "crew_type, analysis_data, created_at"
            ).eq("account_id", account_id).order(
                "created_at", desc=True
            ).limit(5).execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Error fetching recent analysis: {e}")
            return []

    def _fetch_related_macro_insights(self, account_id: str) -> List[Dict[str, Any]]:
        """Fetch macro insights that affect this account."""
        if not self.supabase:
            return []
        try:
            # Get insights where account is in affected_accounts
            result = self.supabase.table("macro_insight_history").select(
                "insight_type, severity, title, narrative"
            ).eq("is_active", True).limit(10).execute()

            # Filter to those affecting this account
            relevant = []
            for insight in result.data or []:
                affected = insight.get("affected_accounts", []) or []
                if account_id in affected or not affected:
                    relevant.append(insight)

            return relevant[:5]
        except Exception as e:
            logger.error(f"Error fetching related macro insights: {e}")
            return []

    def _fetch_recent_meetings(
        self, salesforce_account_id: str, days_back: int = 30
    ) -> List[Dict[str, Any]]:
        """Fetch recent meeting summaries for the account."""
        if not self.supabase or not salesforce_account_id:
            return []
        try:
            cutoff = (datetime.utcnow() - timedelta(days=days_back)).isoformat()
            result = self.supabase.table("transcriptions").select(
                "id, meeting_subject, meeting_date, ai_summary"
            ).eq("salesforce_account_id", salesforce_account_id).gte(
                "meeting_date", cutoff
            ).order("meeting_date", desc=True).limit(5).execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Error fetching recent meetings: {e}")
            return []

    def _fetch_recent_cases(
        self, salesforce_account_id: str, days_back: int = 60
    ) -> List[Dict[str, Any]]:
        """Fetch recent support cases for the account."""
        if not self.supabase or not salesforce_account_id:
            return []
        try:
            cutoff = (datetime.utcnow() - timedelta(days=days_back)).isoformat()
            result = self.supabase.table("cases").select(
                "case_number, subject, status, priority, created_date"
            ).eq("salesforce_account_id", salesforce_account_id).gte(
                "created_date", cutoff
            ).order("created_date", desc=True).limit(10).execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Error fetching recent cases: {e}")
            return []

    def _fetch_metric_context(self, metric_id: str) -> Dict[str, Any]:
        """Fetch context for a metric drilldown (e.g., NRR, pipeline coverage)."""
        if not self.supabase:
            return {}

        context = {"metric_id": metric_id, "details": {}, "contributing_accounts": []}

        try:
            # Different queries based on metric type
            if metric_id == "nrr" or metric_id == "grr":
                result = self.supabase.table("renewal_arr_history").select(
                    "account_name, arr, previous_arr, arr_change, renewal_date, is_won"
                ).order("renewal_date", desc=True).limit(20).execute()
                context["details"] = {
                    "renewals": result.data or [],
                    "total_analyzed": len(result.data or []),
                }

            elif metric_id == "pipeline_coverage":
                result = self.supabase.table("opportunities").select(
                    "name, amount, stage_name, probability, close_date, accounts(name)"
                ).eq("is_closed", False).order("amount", desc=True).limit(20).execute()
                context["details"] = {
                    "pipeline": result.data or [],
                    "total_pipeline": sum(o.get("amount", 0) or 0 for o in result.data or []),
                }

            elif metric_id == "health":
                result = self.supabase.table("accounts").select(
                    "name, health_score, contract_value, account_tier"
                ).lt("health_score", 5).order("contract_value", desc=True).limit(10).execute()
                context["details"] = {
                    "at_risk": result.data or [],
                    "total_at_risk_arr": sum(a.get("contract_value", 0) or 0 for a in result.data or []),
                }

        except Exception as e:
            logger.error(f"Error fetching metric context: {e}")

        return context

    # ─── Data formatting ─────────────────────────────────────────────

    def _format_currency(self, value: Any) -> str:
        """Format a numeric value as currency."""
        try:
            v = float(value) if value else 0
        except (TypeError, ValueError):
            return "$0"
        if v >= 1_000_000:
            return f"${v / 1_000_000:.1f}M"
        if v >= 1_000:
            return f"${v / 1_000:.0f}K"
        return f"${v:.0f}"

    def _format_account_context(
        self,
        account: Dict[str, Any],
        analysis: List[Dict[str, Any]],
        meetings: List[Dict[str, Any]],
        cases: List[Dict[str, Any]],
        macro_insights: List[Dict[str, Any]],
        context_type: str,
    ) -> str:
        """Format all account context for the prompt."""
        parts = []

        # Account overview
        parts.append(f"ACCOUNT: {account.get('name', 'Unknown')}")
        parts.append(f"ARR: {self._format_currency(account.get('contract_value', 0))}")
        parts.append(f"Tier: {account.get('account_tier', 'Unknown')}")
        parts.append(f"Health Score: {account.get('health_score', 'N/A')}")
        parts.append(f"Days Since Contact: {account.get('days_since_last_touch', 'Unknown')}")
        parts.append(f"Contract End: {account.get('contract_end_date', 'Unknown')}")
        parts.append(f"Owner: {account.get('owner_name', 'Unknown')}")
        parts.append("")

        # Recent analysis
        if analysis:
            parts.append("RECENT AI ANALYSIS:")
            for a in analysis[:3]:
                crew = a.get("crew_type", "unknown")
                created = a.get("created_at", "")[:10]
                data = a.get("analysis_data", {})
                summary = data.get("executive_summary", data.get("summary", ""))[:150]
                parts.append(f"  [{crew}] ({created}): {summary}")
            parts.append("")

        # Macro insights affecting this account
        if macro_insights:
            parts.append("SYSTEMIC RISKS AFFECTING ACCOUNT:")
            for i in macro_insights:
                severity = i.get("severity", "unknown").upper()
                title = i.get("title", "Unknown")
                parts.append(f"  [{severity}] {title}")
            parts.append("")

        # Recent meetings
        if meetings:
            parts.append("RECENT MEETINGS:")
            for m in meetings[:3]:
                subject = m.get("meeting_subject", "Unknown")
                date = m.get("meeting_date", "")[:10]
                summary = m.get("ai_summary", "")[:100]
                parts.append(f"  - {subject} ({date}): {summary}")
            parts.append("")

        # Recent cases
        if cases:
            open_cases = [c for c in cases if c.get("status", "").lower() != "closed"]
            if open_cases:
                parts.append("OPEN SUPPORT CASES:")
                for c in open_cases[:5]:
                    priority = c.get("priority", "Normal")
                    subject = c.get("subject", "Unknown")[:50]
                    parts.append(f"  [{priority}] {subject}")
                parts.append("")

        # Context-specific focus
        parts.append(f"ANALYSIS CONTEXT: {context_type.upper()}")
        if context_type == "risk":
            parts.append("Focus on: Why is this account at risk? What are the warning signs?")
        elif context_type == "renewal":
            parts.append("Focus on: What's the renewal outlook? Key concerns for retention?")
        elif context_type == "expansion":
            parts.append("Focus on: What expansion opportunities exist? Blockers to growth?")
        elif context_type == "engagement":
            parts.append("Focus on: What's the engagement level? Are we under/over-communicating?")

        return "\n".join(parts)

    def _format_metric_context(
        self, metric_context: Dict[str, Any], context_type: str
    ) -> str:
        """Format metric context for the prompt."""
        metric_id = metric_context.get("metric_id", "unknown")
        details = metric_context.get("details", {})

        parts = [f"METRIC: {metric_id.upper()}"]

        if metric_id in ("nrr", "grr"):
            renewals = details.get("renewals", [])
            won = [r for r in renewals if r.get("is_won")]
            lost = [r for r in renewals if not r.get("is_won")]
            parts.append(f"Recent renewals analyzed: {len(renewals)}")
            parts.append(f"Won: {len(won)}, Lost: {len(lost)}")

            if lost:
                parts.append("Lost renewals:")
                for r in lost[:5]:
                    parts.append(
                        f"  - {r.get('account_name')}: {self._format_currency(r.get('arr_change', 0))}"
                    )

        elif metric_id == "pipeline_coverage":
            pipeline = details.get("pipeline", [])
            total = details.get("total_pipeline", 0)
            parts.append(f"Total open pipeline: {self._format_currency(total)}")
            parts.append("Top deals:")
            for p in pipeline[:5]:
                account = p.get("accounts", {})
                parts.append(
                    f"  - {p.get('name')} ({account.get('name', 'Unknown')}): "
                    f"{self._format_currency(p.get('amount', 0))}"
                )

        elif metric_id == "health":
            at_risk = details.get("at_risk", [])
            total_arr = details.get("total_at_risk_arr", 0)
            parts.append(f"Accounts at critical risk (health < 5): {len(at_risk)}")
            parts.append(f"Total ARR at risk: {self._format_currency(total_arr)}")
            for a in at_risk[:5]:
                parts.append(
                    f"  - {a.get('name')}: {self._format_currency(a.get('contract_value', 0))} "
                    f"(health: {a.get('health_score', 0)})"
                )

        parts.append(f"\nANALYSIS CONTEXT: {context_type.upper()}")

        return "\n".join(parts)

    # ─── Agents ──────────────────────────────────────────────────────

    def _create_agents(self) -> None:
        """Create the drilldown analyst agent."""
        self.analyst = self.create_agent_from_config(
            "contextual_drilldown_analyst",
            role_default="Quick Insight Analyst",
            goal_default=(
                "Provide concise, actionable synthesis explaining why an account or "
                "metric is flagged, with clear next steps"
            ),
            backstory_default=(
                "You are a rapid-response analyst specializing in distilling complex "
                "customer data into brief, actionable insights. Executives trust you to "
                "quickly explain 'why is this flagged' without burying them in details. "
                "You always lead with the most critical finding, provide 3-5 bullet points "
                "of context, and end with clear recommended actions. You value speed and "
                "clarity over exhaustive analysis."
            ),
        )

    # ─── Tasks ───────────────────────────────────────────────────────

    def _build_account_drilldown_task(
        self, formatted_context: str
    ) -> Task:
        """Build the account drilldown task."""
        task_config = self._get_task_config("contextual_account_drilldown")

        description = task_config.get("description", "") or (
            "Generate a quick synthesis for this account drilldown.\n\n"
            "{context}\n\n"
            "Provide a concise analysis in JSON format:\n"
            "{{\n"
            '  "synthesis": "One paragraph (2-3 sentences) summarizing why this account needs attention",\n'
            '  "bullets": ["3-5 key points explaining the situation"],\n'
            '  "recommended_actions": [{{"action": "...", "priority": "immediate|this_week|this_month"}}],\n'
            '  "related_signals": ["Any patterns or signals from meetings/cases"]\n'
            "}}\n\n"
            "Be concise. This needs to be digestible in under 30 seconds."
        )

        return Task(
            description=description.format(context=formatted_context),
            expected_output=task_config.get(
                "expected_output",
                "A JSON object with synthesis, bullets, recommended_actions, and related_signals."
            ),
            agent=self.analyst,
        )

    def _build_metric_drilldown_task(
        self, formatted_context: str
    ) -> Task:
        """Build the metric drilldown task."""
        task_config = self._get_task_config("contextual_metric_drilldown")

        description = task_config.get("description", "") or (
            "Generate a quick synthesis for this metric drilldown.\n\n"
            "{context}\n\n"
            "Provide a concise analysis in JSON format:\n"
            "{{\n"
            '  "synthesis": "One paragraph (2-3 sentences) explaining why this metric needs attention",\n'
            '  "bullets": ["3-5 key points about contributing factors"],\n'
            '  "recommended_actions": [{{"action": "...", "priority": "immediate|this_week|this_month"}}],\n'
            '  "contributing_accounts": ["Account names most impacting this metric"]\n'
            "}}\n\n"
            "Be concise. This needs to be digestible in under 30 seconds."
        )

        return Task(
            description=description.format(context=formatted_context),
            expected_output=task_config.get(
                "expected_output",
                "A JSON object with synthesis, bullets, recommended_actions, and contributing_accounts."
            ),
            agent=self.analyst,
        )

    # ─── Main run method ─────────────────────────────────────────────

    def run(
        self,
        entity_type: str,
        entity_id: str,
        context: str = "risk",
        user_id: Optional[str] = None,
        step_callback: Optional[callable] = None,
    ) -> Dict[str, Any]:
        """
        Run the contextual drilldown crew.

        Args:
            entity_type: One of: account, metric, renewal
            entity_id: The ID of the entity (account UUID, metric name, etc.)
            context: One of: risk, renewal, expansion, engagement
            user_id: Optional user ID for AI settings
            step_callback: Optional progress callback

        Returns:
            Dict with drilldown synthesis and metadata
        """
        if entity_type not in ENTITY_TYPES:
            return {
                "success": False,
                "error": f"Invalid entity_type: {entity_type}. Must be one of: {ENTITY_TYPES}",
            }

        if context not in CONTEXT_TYPES:
            context = "risk"  # Default to risk context

        if step_callback:
            step_callback(f"Fetching {entity_type} data...")

        # Create agents
        self._create_agents()

        # Handle different entity types
        if entity_type == "account" or entity_type == "renewal":
            # Fetch account data
            account = self._fetch_account_data(entity_id)
            if not account:
                return {
                    "success": False,
                    "error": f"Account not found: {entity_id}",
                }

            sf_account_id = account.get("salesforce_id", "")

            if step_callback:
                step_callback("Gathering account context...")

            # Fetch related data
            analysis = self._fetch_recent_analysis(entity_id)
            meetings = self._fetch_recent_meetings(sf_account_id)
            cases = self._fetch_recent_cases(sf_account_id)
            macro_insights = self._fetch_related_macro_insights(entity_id)

            # Format context
            formatted_context = self._format_account_context(
                account, analysis, meetings, cases, macro_insights, context
            )

            # Build task
            task = self._build_account_drilldown_task(formatted_context)

            # Track additional data
            related_meetings = [
                {"id": m.get("id"), "subject": m.get("meeting_subject"), "date": m.get("meeting_date")}
                for m in meetings
            ]
            related_cases = [
                {"number": c.get("case_number"), "subject": c.get("subject"), "status": c.get("status")}
                for c in cases
            ]

        elif entity_type == "metric":
            if step_callback:
                step_callback("Gathering metric context...")

            metric_context = self._fetch_metric_context(entity_id)
            formatted_context = self._format_metric_context(metric_context, context)
            task = self._build_metric_drilldown_task(formatted_context)
            related_meetings = []
            related_cases = []

        else:
            return {
                "success": False,
                "error": f"Unsupported entity_type: {entity_type}",
            }

        if step_callback:
            step_callback("Generating synthesis...")

        # Run the crew
        crew = Crew(
            name="Contextual Drilldown Crew",
            agents=[self.analyst],
            tasks=[task],
            process=Process.sequential,
            verbose=False,
        )

        result = crew.kickoff()
        result_text = str(result)

        # Parse the JSON result
        parsed_result = self._parse_json_result(
            result_text,
            default={
                "synthesis": result_text[:300] if result_text else "Unable to generate synthesis.",
                "bullets": [],
                "recommended_actions": [],
            }
        )

        # Get model info
        model_name = getattr(self.llm, "model", "unknown")
        provider = "openai"
        if "claude" in model_name.lower() or "anthropic" in model_name.lower():
            provider = "anthropic"
        elif "gemini" in model_name.lower():
            provider = "google"

        return {
            "success": True,
            "synthesis": parsed_result.get("synthesis"),
            "bullets": parsed_result.get("bullets", []),
            "recommended_actions": parsed_result.get("recommended_actions", []),
            "related_meetings": related_meetings if entity_type in ("account", "renewal") else [],
            "related_cases": related_cases if entity_type in ("account", "renewal") else [],
            "contributing_accounts": parsed_result.get("contributing_accounts", []),
            "related_signals": parsed_result.get("related_signals", []),
            "entity_type": entity_type,
            "entity_id": entity_id,
            "context": context,
            "generated_at": datetime.utcnow().isoformat(),
            "provider": provider,
            "model": model_name,
        }
