"""
Product Intelligence Crew - Analyzes support cases to identify themes, patterns, and actions.

This crew processes pre-classified support cases for a given period to produce:
- Per-category theme analysis with top issues, recurring patterns, and emerging themes
- Taxonomy assignments linking cases to existing L2/L3 taxonomy entries
- Actionable recommendations for Product teams, prioritized by impact
- Version correlation insights

Supports map-reduce batching for high-volume periods (>200 cases):
- Below 200: cases passed directly to Theme Analyst
- Above 200: batched into ~50-case groups, summarized, then analyzed
"""

import json
import logging
import math
from typing import Any, Callable, Dict, List, Optional

from crewai import Agent, Crew, Task

from .base_crew import BaseCrew
from ..utils import extract_json_from_llm_response

logger = logging.getLogger(__name__)

# Max cases before triggering map-reduce
# Each case is ~125 tokens with CASE_DESC_LIMIT=200. Claude Sonnet 4.6 has 200K context.
# At 800 cases × 125 tokens = 100K tokens input — still leaves room for prompt + output.
# Below this threshold, cases go directly to Theme Analyst (2 LLM calls vs 11+).
MAP_REDUCE_THRESHOLD = 800
# Target batch size for map-reduce (larger = fewer API calls, helps with rate limits)
BATCH_SIZE = 200
# Max chars of description to include per case (shorter = more cases fit in context)
CASE_DESC_LIMIT = 200


class ProductIntelligenceCrew(BaseCrew):
    """Crew that analyzes support cases to identify themes, patterns, and recommended actions."""

    def _format_case_for_context(self, case: Dict[str, Any]) -> str:
        """Format a single case into a compact context string (~500 tokens)."""
        subject = case.get("subject", "No subject")
        description = (case.get("description") or "")[:CASE_DESC_LIMIT]
        product = case.get("support_product") or case.get("product") or "Unknown"
        version = case.get("package_version_at_creation", "N/A")
        priority = case.get("priority", "Unknown")
        status = case.get("status", "Unknown")
        pi_category = case.get("pi_category", "uncategorized")
        case_number = case.get("case_number", "N/A")
        account = case.get("account_name", "Unknown")

        return (
            f"[Case {case_number}] ({pi_category}) {subject}\n"
            f"  Product: {product} | Version: {version} | Priority: {priority} | Status: {status}\n"
            f"  Account: {account}\n"
            f"  Description: {description}\n"
        )

    def _format_cases_block(self, cases: List[Dict[str, Any]]) -> str:
        """Format a list of cases into a context block."""
        if not cases:
            return "NO CASES PROVIDED"
        lines = []
        for case in cases:
            lines.append(self._format_case_for_context(case))
        return "\n".join(lines)

    def _build_category_summary(self, cases: List[Dict[str, Any]]) -> str:
        """Build a quick summary of case counts by category."""
        counts: Dict[str, int] = {}
        for case in cases:
            cat = case.get("pi_category", "uncategorized")
            counts[cat] = counts.get(cat, 0) + 1
        lines = [f"  {cat}: {count} cases" for cat, count in sorted(counts.items(), key=lambda x: -x[1])]
        return "\n".join(lines)

    def _build_product_summary(self, cases: List[Dict[str, Any]]) -> str:
        """Build a quick summary of case counts by product."""
        counts: Dict[str, int] = {}
        for case in cases:
            product = case.get("support_product") or case.get("product") or "Unknown"
            counts[product] = counts.get(product, 0) + 1
        lines = [f"  {product}: {count} cases" for product, count in sorted(counts.items(), key=lambda x: -x[1])]
        return "\n".join(lines)

    def _format_taxonomy_context(self, taxonomy: List[Dict[str, Any]]) -> str:
        """Format existing taxonomy entries for context."""
        if not taxonomy:
            return "NO EXISTING TAXONOMY ENTRIES"
        lines = []
        for entry in taxonomy:
            l2 = entry.get("l2_category", "Unknown")
            l3 = entry.get("l3_category", "")
            desc = entry.get("description", "")
            l3_part = f" > {l3}" if l3 else ""
            desc_part = f" - {desc}" if desc else ""
            lines.append(f"  {l2}{l3_part}{desc_part}")
        return "\n".join(lines)

    def _format_version_distribution(self, version_dist: List[Dict[str, Any]]) -> str:
        """Format version distribution data for context."""
        if not version_dist:
            return "NO VERSION DISTRIBUTION DATA"
        lines = []
        for v in version_dist:
            version = v.get("version", "Unknown")
            count = v.get("case_count", 0)
            accounts = v.get("accounts_affected", 0)
            first_install = v.get("first_install_date", "N/A")
            lines.append(f"  {version}: {count} cases, {accounts} accounts (first install: {first_install})")
        return "\n".join(lines)

    def _format_prior_period(self, prior: Dict[str, Any]) -> str:
        """Format prior period summary for trend comparison."""
        if not prior:
            return "NO PRIOR PERIOD DATA AVAILABLE"
        return json.dumps(prior, indent=2, default=str)

    def _run_map_reduce(
        self,
        cases: List[Dict[str, Any]],
        _emit_progress: Callable,
    ) -> str:
        """Run map phase: batch cases into groups, summarize each, return combined summaries.

        Returns a string of batch summaries to pass to the Theme Analyst instead of raw cases.
        """
        num_batches = math.ceil(len(cases) / BATCH_SIZE)
        _emit_progress("map_reduce", f"High volume ({len(cases)} cases). Running map-reduce with {num_batches} batches...")

        batch_summarizer = Agent(
            role="Case Batch Summarizer",
            goal="Summarize a batch of support cases into key themes, patterns, and clusters",
            backstory="""You are a support data analyst skilled at rapidly identifying patterns
            across batches of support cases. You extract the most important themes, group similar
            issues together, and note severity and frequency. You produce concise, structured
            summaries that preserve the essential information from each batch.""",
            llm=self.llm,
            verbose=False,
            allow_delegation=False,
        )

        batch_tasks = []
        for i in range(num_batches):
            start = i * BATCH_SIZE
            end = min(start + BATCH_SIZE, len(cases))
            batch = cases[start:end]
            batch_context = self._format_cases_block(batch)

            task = Task(
                description=f"""Summarize batch {i + 1} of {num_batches} ({len(batch)} cases).

CASES IN THIS BATCH:
{batch_context}

Produce a structured summary of this batch:
1. Key themes/clusters found (group similar issues)
2. For each theme: issue description, case count, severity level, affected products
3. Notable patterns or emerging issues
4. Any version-specific correlations

Be concise but preserve all important signals. This summary will be used by a downstream analyst.""",
                expected_output=f"""Batch {i + 1} summary with:
- Theme clusters with case counts and severity
- Affected products per theme
- Notable patterns
- Version correlations if any""",
                agent=batch_summarizer,
            )
            batch_tasks.append(task)

        # Run batch summarization crew
        _emit_progress("map_reduce", f"Summarizing {num_batches} batches...")
        batch_crew = Crew(
            agents=[batch_summarizer],
            tasks=batch_tasks,
            verbose=False,
        )
        batch_result = batch_crew.kickoff()

        # Collect all batch outputs
        batch_summaries = []
        if hasattr(batch_result, 'tasks_output') and batch_result.tasks_output:
            for idx, task_output in enumerate(batch_result.tasks_output):
                batch_summaries.append(f"=== BATCH {idx + 1} SUMMARY ===\n{str(task_output)}")
        else:
            # Fallback: use the raw result
            batch_summaries.append(str(batch_result))

        combined = "\n\n".join(batch_summaries)
        _emit_progress("map_reduce", "Batch summarization complete. Proceeding to theme analysis...")
        return combined

    def run(
        self,
        cases_data: List[Dict[str, Any]],
        existing_taxonomy: List[Dict[str, Any]],
        prior_period_summary: Dict[str, Any],
        version_distribution: List[Dict[str, Any]],
        period_info: Dict[str, Any],
        send_progress: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """
        Run the product intelligence analysis.

        Args:
            cases_data: Pre-classified support cases for the period
            existing_taxonomy: Existing pi_taxonomy entries for reference
            prior_period_summary: Summary data from prior period for trend comparison
            version_distribution: Package version distribution with case counts
            period_info: Dict with type, start, end (e.g. {"type": "monthly", "start": "2026-01-01", "end": "2026-01-31"})
            send_progress: Optional callback for streaming progress updates

        Returns:
            Dict with executive_summary, version_insights, and per-category analysis
        """
        period_type = period_info.get("type", "unknown")
        period_start = period_info.get("start", "N/A")
        period_end = period_info.get("end", "N/A")
        total_cases = len(cases_data)

        logger.info(f"Running product intelligence analysis: {total_cases} cases, {period_type} period ({period_start} to {period_end})")

        def _emit_progress(step: str, message: str):
            if send_progress:
                send_progress(step, message)
            logger.info(f"[{step}] {message}")

        _emit_progress("init", f"Starting product intelligence analysis for {total_cases} cases ({period_type}: {period_start} to {period_end})")

        # Build context strings
        category_summary = self._build_category_summary(cases_data)
        product_summary = self._build_product_summary(cases_data)
        taxonomy_context = self._format_taxonomy_context(existing_taxonomy)
        version_context = self._format_version_distribution(version_distribution)
        prior_context = self._format_prior_period(prior_period_summary)

        # Decide: direct analysis vs map-reduce
        if total_cases > MAP_REDUCE_THRESHOLD:
            # Map-reduce: batch summarize first, then analyze summaries
            cases_input = self._run_map_reduce(cases_data, _emit_progress)
            cases_input_label = "BATCH SUMMARIES (map-reduce applied due to high volume)"
        else:
            # Direct: pass all cases to Theme Analyst
            cases_input = self._format_cases_block(cases_data)
            cases_input_label = "SUPPORT CASES"

        # =====================================================================
        # Agent 1: Theme Analyst
        # =====================================================================
        _emit_progress("theme_analysis", "Analyzing themes and patterns across cases...")

        theme_analyst = Agent(
            role="Support Theme Analyst",
            goal="Identify top issues, recurring patterns, and emerging themes across support cases. Assign cases to existing taxonomy entries where applicable.",
            backstory="""You are an expert support data analyst specializing in product intelligence.
            You excel at identifying patterns across large volumes of support cases, grouping similar
            issues into meaningful themes, and spotting emerging trends. You understand software product
            support deeply - recognizing bug patterns, feature gaps, documentation issues, and
            configuration challenges. You always consider version context and compare against prior
            periods to identify what is new vs ongoing. You assign cases to existing taxonomy categories
            when they match, and flag new themes that may need new taxonomy entries.""",
            llm=self.llm,
            verbose=False,
            allow_delegation=False,
        )

        theme_task = Task(
            description=f"""Analyze support cases for the {period_type} period ({period_start} to {period_end}).

PERIOD OVERVIEW:
- Total cases: {total_cases}
- Period: {period_type} ({period_start} to {period_end})

CASE DISTRIBUTION BY CATEGORY:
{category_summary}

CASE DISTRIBUTION BY PRODUCT:
{product_summary}

EXISTING TAXONOMY (assign cases to these L2/L3 entries where applicable):
{taxonomy_context}

VERSION DISTRIBUTION:
{version_context}

PRIOR PERIOD SUMMARY (for trend comparison):
{prior_context}

{cases_input_label}:
{cases_input}

YOUR ANALYSIS SHOULD COVER:

1. **Per-Category Theme Analysis**: For each PI category (bug, feature_request, documentation, configuration, integration, performance, etc.):
   - Top issues with case counts and severity
   - Group similar cases into topic clusters (e.g., "API Errors", "Routing Failures")
   - For each topic group: name, case count, summary, affected product(s), severity
   - Within each topic group, identify specific issue types
   - Flag which patterns are ongoing vs newly emerging this period

2. **Taxonomy Assignments**: Where cases match existing L2/L3 taxonomy entries, note the assignment. Flag themes that need new taxonomy entries.

3. **Version Insights**: Correlate issues with package versions. Identify if specific versions introduced new problems or if certain versions have disproportionate case counts.

4. **Trend Comparison**: Compare against prior period data. What is improving? What is getting worse? What is new?

Be thorough and data-driven. Every observation should reference specific case counts and affected products.""",
            expected_output="""Structured theme analysis covering:
- Per-category breakdown with topic groups and issue types
- Case counts, severity levels, and affected products for each theme
- Taxonomy assignments and suggestions for new entries
- Version correlation findings
- Trend comparison with prior period (improving, worsening, new)""",
            agent=theme_analyst,
        )

        # =====================================================================
        # Agent 2: Action Synthesizer
        # =====================================================================
        _emit_progress("action_synthesis", "Synthesizing actionable recommendations...")

        action_synthesizer = Agent(
            role="Product Intelligence Action Synthesizer",
            goal="Produce actionable, prioritized recommendations for Product teams based on support case theme analysis.",
            backstory="""You are a senior product strategist who translates support data insights
            into clear, prioritized actions for Product teams. You understand how to weigh issue
            severity, frequency, customer impact, and version context to recommend the most
            impactful improvements. You produce recommendations that are specific, actionable,
            and tied to evidence from the case data. You also generate executive summaries that
            communicate the key takeaways concisely.""",
            llm=self.llm,
            verbose=False,
            allow_delegation=False,
        )

        action_task = Task(
            description=f"""Based on the theme analysis, produce actionable recommendations and a final structured report.

PERIOD CONTEXT:
- Period: {period_type} ({period_start} to {period_end})
- Total cases: {total_cases}

VERSION DISTRIBUTION:
{version_context}

Using the theme analysis provided, produce:

1. **Executive Summary**: 2-4 sentence overview of the most important findings and recommended priorities for this period.

2. **Version Insights**: Summary of version-related patterns plus specific release correlations with suggested actions.

3. **Per-Category Analysis with Actions**: For each category (bug, feature_request, documentation, configuration, integration, performance, etc.):
   - Category-level analysis summary and suggested actions
   - Topic groups with:
     - Group name, case count, summary, suggested action, affected product
     - Within each group: specific issue types with name, case count, severity, summary, suggested action

4. **Prioritization**: Rank suggested actions by impact (consider case count, severity, customer breadth, and whether the issue is growing).

IMPORTANT: Return your response as a single valid JSON object with this exact structure:

{{
  "executive_summary": "...",
  "version_insights": {{
    "summary": "...",
    "release_correlations": [
      {{"version": "...", "accounts_affected": 0, "case_count": 0, "notable_pattern": "...", "first_install_date": "...", "suggested_action": "..."}}
    ]
  }},
  "categories": {{
    "bug": {{
      "count": 0,
      "analysis": "...",
      "suggested_actions": ["..."],
      "topic_groups": [
        {{
          "name": "...",
          "case_count": 0,
          "summary": "...",
          "suggested_action": "...",
          "affected_product": "...",
          "issue_types": [
            {{"name": "...", "case_count": 0, "severity": "high|medium|low", "summary": "...", "suggested_action": "..."}}
          ]
        }}
      ]
    }},
    "feature_request": {{ ... }},
    "documentation": {{ ... }},
    "configuration": {{ ... }}
  }}
}}

Include ALL categories that have cases. If a category has zero cases this period, omit it.
Use "high", "medium", or "low" for severity values.
Ensure all counts are integers and all strings are properly escaped.""",
            expected_output="""A single valid JSON object containing:
- executive_summary (string)
- version_insights (object with summary and release_correlations array)
- categories (object with per-category analysis, topic_groups, and issue_types)

All data must be evidence-based with accurate case counts from the theme analysis.""",
            agent=action_synthesizer,
            context=[theme_task],
        )

        # =====================================================================
        # Create and run crew
        # =====================================================================
        _emit_progress("crew_run", "Running analysis crew...")

        crew = Crew(
            agents=[theme_analyst, action_synthesizer],
            tasks=[theme_task, action_task],
            verbose=False,
        )

        result = crew.kickoff()

        _emit_progress("complete", "Product intelligence analysis complete!")

        # Parse result
        result_str = str(result)
        default = {
            "executive_summary": result_str,
            "version_insights": {
                "summary": "",
                "release_correlations": [],
            },
            "categories": {},
            "raw_result": result_str,
        }
        parsed_result = extract_json_from_llm_response(result_str, default=default)
        parsed_result["provider"] = "crewai"
        parsed_result["model"] = getattr(self.llm, 'model', 'unknown')
        parsed_result["total_cases_analyzed"] = total_cases
        parsed_result["period"] = period_info
        parsed_result["used_map_reduce"] = total_cases > MAP_REDUCE_THRESHOLD

        return parsed_result
