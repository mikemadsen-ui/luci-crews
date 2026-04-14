"""
AI SDR Crew

Batch job that researches prospect accounts, finds the right ICP contact,
drafts personalized content for all 4 Outreach sequence steps, runs QA,
and gates enrollment behind human review.

Sequence structure (all 4 verticals — fintech, insurance, smb, emea):
  Step 1: MANUAL task in Outreach queue — human reviews and sends
  Steps 2-4: Automated — fire on their scheduled days after Step 1 is sent

V1 gates (two layers before any prospect receives Step 1):
  Gate 1: human_input=True on enroll_prospect task (crew pauses for approval)
  Gate 2: Step 1 is manual in Outreach — human sends from task queue

Outreach variables populated at enrollment time:
  ai_subject_1, ai_body_1, ai_body_2, ai_body_3, ai_subject_4, ai_body_4

Reply handler runs as a SEPARATE process — see services/reply_monitor.py.
Do not add the reply handler to this crew.
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import yaml
from crewai import Crew, LLM, Process, Task

from .base_crew import BaseCrew
from ..ai_settings_helper import create_llm_for_provider
from ..mcp_client import (
    avoma_search_meetings,
    graph_account_network,
    luci_list_accounts,
    luci_list_meetings,
    luci_search_portfolio,
    outreach_add_prospect_to_sequence,
    outreach_list_sequences,
    salesforce_get_record,
    salesforce_query,
    zoominfo_enrich_company,
    zoominfo_search_contacts,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sequence IDs — all 4 verticals
# ---------------------------------------------------------------------------

SEQUENCE_IDS: Dict[str, Optional[str]] = {
    "fintech":   "5724",   # FY26 Q2 - AI SDR Pilot (FinTech)
    "insurance": "5732",   # FY26 Q2 - AI SDR Pilot (Insurance)
    "smb":       "5733",   # FY26 Q2 - AI SDR Pilot (SMB)
    "emea":      "5734",   # FY26 Q2 - AI SDR Pilot (EMEA)
}

# ---------------------------------------------------------------------------
# QA config loader
# ---------------------------------------------------------------------------

def load_qa_config() -> Dict[str, Any]:
    """Load AI SDR QA configuration from ai_sdr_qa_config.yaml."""
    config_path = os.path.join(
        os.path.dirname(__file__),
        "../config/ai_sdr_qa_config.yaml",
    )
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Crew class
# ---------------------------------------------------------------------------

class AiSdrCrew(BaseCrew):
    """
    AI SDR crew — researches accounts, finds ICP contacts, drafts 4-step email
    sequences, runs QA, and gates Outreach enrollment behind human review.

    Always runs on Anthropic (claude-sonnet-4-6) regardless of user settings.
    memory=False — context flows via task context=[] chain, not ChromaDB embeddings.

    Usage:
        crew = AiSdrCrew()
        result = crew.run(
            accounts=[{"account_name": "Acme", "salesforce_id": "0015A..."}],
            vertical="fintech",
            dry_run=True,
            enrollment_enabled=False,
        )
    """

    # AI SDR always runs on Anthropic — override BaseCrew's dynamic model selection
    _ANTHROPIC_MODEL = "claude-sonnet-4-5-20250929"

    # BaseCrew auto-initializes self.supabase from SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY
    needs_supabase = True

    def _init_llm(self, user_id, llm):
        """Always use Anthropic for the AI SDR crew — ignore user model settings."""
        if llm is not None:
            return llm  # respect explicit override (e.g. tests)
        return create_llm_for_provider(
            provider="anthropic",
            model_id=self._ANTHROPIC_MODEL,
            api_key=os.getenv("ANTHROPIC_API_KEY"),
        )

    # ---------------------------------------------------------------------------
    # Supabase logging helpers
    # ---------------------------------------------------------------------------

    @staticmethod
    def _supabase_logging_enabled(qa_config: Dict[str, Any]) -> bool:
        return qa_config.get("logging", {}) \
                        .get("supabase_logging", {}) \
                        .get("enabled", False)

    def _log_batch_run(
        self,
        run_id: str,
        started_at: datetime,
        completed_at: datetime,
        vertical: str,
        total: int,
        processed: int,
        skipped_count: int,
        enrollment_enabled: bool,
        dry_run: bool,
    ) -> None:
        """Insert one row to ai_sdr_batch_runs. Never raises — log and continue."""
        if not self.supabase:
            return
        try:
            self.supabase.table("ai_sdr_batch_runs").insert({
                "run_id": run_id,
                "started_at": started_at.isoformat(),
                "completed_at": completed_at.isoformat(),
                "vertical": vertical,
                "total_accounts": total,
                "processed": processed,
                "skipped": skipped_count,
                "flagged": 0,    # derived from ai_sdr_account_results rows
                "enrolled": 0,   # derived from ai_sdr_account_results rows
                "enrollment_enabled": enrollment_enabled,
                "dry_run": dry_run,
            }).execute()
            logger.info(f"[AI SDR] Logged batch run {run_id} to Supabase")
        except Exception as e:
            logger.error(f"[AI SDR] Supabase batch_run log failed: {e}")

    def _log_account_result(
        self,
        run_id: str,
        account: Dict[str, Any],
        vertical: str,
        result: Any,
        sequence_id: Optional[str],
    ) -> None:
        """Insert one row to ai_sdr_account_results. Never raises — log and continue."""
        if not self.supabase:
            return
        try:
            parsed: Dict[str, Any] = {}
            if hasattr(result, "json_dict") and result.json_dict:
                parsed = result.json_dict
            elif hasattr(result, "raw"):
                try:
                    parsed = json.loads(result.raw)
                except (json.JSONDecodeError, TypeError):
                    pass

            contact = parsed.get("target_contact") or {}

            self.supabase.table("ai_sdr_account_results").insert({
                "run_id": run_id,
                "account_name": account.get("account_name"),
                "salesforce_id": account.get("salesforce_id"),
                "vertical": vertical,
                "contact_name": contact.get("name"),
                "contact_title": contact.get("title"),
                "contact_email": contact.get("email"),
                "primary_signal_type": parsed.get("primary_signal_type"),
                "primary_signal_value": parsed.get("primary_signal_value"),
                "confidence_score": parsed.get("confidence"),
                "flagged": parsed.get("flagged", False),
                "flag_reason": parsed.get("flag_reason"),
                "enrolled": parsed.get("enrolled", False),
                "sequence_id": sequence_id,
            }).execute()
        except Exception as e:
            logger.error(
                f"[AI SDR] Supabase account_result log failed for "
                f"{account.get('account_name')}: {e}"
            )

    def _create_agents(self) -> None:
        """
        Create all 5 batch crew agents.
        verbose=True overrides agents.yaml verbose: false — needed for v1 debugging.
        Remove verbose=True overrides when promoting to production.
        """
        # Researcher: full data-gathering stack in call order —
        # Step 1: salesforce_query       — validate prospect, check open opps
        # Step 2: graph_account_network  — account_name (partial match, no UUID)
        # Step 3: zoominfo_enrich_company — firmographics (credits — after SFDC)
        # Step 4: zoominfo_search_contacts — find ICP contact (no credits)
        # Step 5: luci_search_portfolio  — signal search (threshold 0.35)
        # Step 6: luci_list_meetings     — prior LD contact check (search=account_name)
        # NOTE: zoominfo_contact_research is NOT included — requires ZoomInfo contact ID,
        # consumes AI credits per query. SDR crew uses zoominfo_search_contacts only.
        self.researcher = self.create_agent_from_config(
            "sdr_prospect_researcher",
            tools=[
                salesforce_query,
                salesforce_get_record,
                graph_account_network,      # Step 2: account_name, no UUID needed
                zoominfo_enrich_company,    # Step 3: credits — only after SFDC passes
                zoominfo_search_contacts,   # Step 4: no credits
                luci_search_portfolio,      # Step 5: threshold 0.35, array filter
                luci_list_meetings,         # Step 6: search=account_name, UUID optional
            ],
        )

        # Signal reader: compiles and distills researcher findings into
        # writer-ready signals. Has avoma + luci tools for any follow-up lookups.
        self.signal_reader = self.create_agent_from_config(
            "sdr_signal_reader",
            tools=[
                luci_list_accounts,         # UUID resolution if needed
                luci_search_portfolio,      # follow-up signal queries
                avoma_search_meetings,      # meeting history (prior relationship check)
            ],
        )

        self.writer = self.create_agent_from_config(
            "sdr_email_writer",
        )

        self.qa_reviewer = self.create_agent_from_config(
            "sdr_qa_reviewer",
        )

        self.enrollment_agent = self.create_agent_from_config(
            "sdr_enrollment_agent",
            tools=[
                outreach_list_sequences,
                outreach_add_prospect_to_sequence,
            ],
        )

    @staticmethod
    def _fmt(template: str, **kwargs) -> str:
        """
        Safe string substitution that ignores literal curly braces in task
        descriptions (e.g. JSON output schema examples).

        Uses str.replace() for each known placeholder instead of str.format(),
        so {account_name} inside a JSON example never triggers a KeyError.
        """
        result = template
        for key, value in kwargs.items():
            result = result.replace("{" + key + "}", str(value))
        return result

    def _create_tasks(
        self,
        account: Dict[str, Any],
        vertical: str,
        dry_run: bool,
        enrollment_enabled: bool,
        qa_config: Dict[str, Any],
        sequence_id: Optional[str],
        reply_inbox: str = "mike.madsen@leandata.com",
    ) -> List[Task]:
        """
        Build the 5-task chain for a single account.

        Descriptions are formatted with static inputs known at call time.
        Dynamic data (previous task outputs) flows through context=[...].
        The placeholder tokens for prior task outputs are replaced with a
        context note so the agent knows where to look.
        """
        research_cfg  = self._get_task_config("research_prospect")
        signals_cfg   = self._get_task_config("gather_signals")
        draft_cfg     = self._get_task_config("draft_email")
        qa_cfg        = self._get_task_config("review_and_score")
        enroll_cfg    = self._get_task_config("enroll_prospect")

        # ── Task 1: Research ────────────────────────────────────────────────
        research_task = Task(
            description=self._fmt(
                research_cfg["description"],
                accounts=json.dumps([account], indent=2),
                vertical=vertical,
                dry_run=dry_run,
            ),
            expected_output=research_cfg["expected_output"],
            agent=self.researcher,
        )

        # ── Task 2: Gather signals ──────────────────────────────────────────
        # research_output flows via context — placeholder replaced with note
        signals_task = Task(
            description=self._fmt(
                signals_cfg["description"],
                research_output="[Read from research_prospect task context]",
            ),
            expected_output=signals_cfg["expected_output"],
            agent=self.signal_reader,
            context=[research_task],
        )

        # ── Task 3: Draft email ─────────────────────────────────────────────
        draft_task = Task(
            description=self._fmt(
                draft_cfg["description"],
                research_output="[Read from research_prospect task context]",
                signals_output="[Read from gather_signals task context]",
                vertical=vertical,
            ),
            expected_output=draft_cfg["expected_output"],
            agent=self.writer,
            context=[research_task, signals_task],
        )

        # ── Task 4: QA review ───────────────────────────────────────────────
        qa_task = Task(
            description=self._fmt(
                qa_cfg["description"],
                research_output="[Read from research_prospect task context]",
                signals_output="[Read from gather_signals task context]",
                drafts_output="[Read from draft_email task context]",
                dry_run=dry_run,
            ),
            expected_output=qa_cfg["expected_output"],
            agent=self.qa_reviewer,
            context=[research_task, signals_task, draft_task],
        )

        # ── Task 5: Enroll ──────────────────────────────────────────────────
        # human_input only when actually enrolling — calling input() with no
        # terminal (web server / asyncio context) raises EOFError.
        # Gate 1 is active only when enrollment_enabled=True.
        # Gate 2: Step 1 in Outreach is MANUAL — sits in task queue until sent.
        enroll_task = Task(
            description=self._fmt(
                enroll_cfg["description"],
                review_queue="[Read from review_and_score task context]",
                enrollment_enabled=enrollment_enabled,
                dry_run=dry_run,
                qa_config=json.dumps(qa_config, indent=2),
                sequence_id=sequence_id or "NOT_CONFIGURED",
            ),
            expected_output=enroll_cfg["expected_output"],
            agent=self.enrollment_agent,
            context=[qa_task],
            human_input=enrollment_enabled,  # Gate 1: only pause when actually enrolling
        )

        return [research_task, signals_task, draft_task, qa_task, enroll_task]

    def _run_single_account(
        self,
        account: Dict[str, Any],
        vertical: str,
        dry_run: bool,
        enrollment_enabled: bool,
        qa_config: Dict[str, Any],
        sequence_id: Optional[str],
    ) -> Any:
        """
        Run the full 5-task chain for one account.
        Agents are created once in run() and reused across accounts.
        A new Crew and task list is created per account.
        """
        tasks = self._create_tasks(
            account=account,
            vertical=vertical,
            dry_run=dry_run,
            enrollment_enabled=enrollment_enabled,
            qa_config=qa_config,
            sequence_id=sequence_id,
        )

        crew = Crew(
            agents=[
                self.researcher,
                self.signal_reader,
                self.writer,
                self.qa_reviewer,
                self.enrollment_agent,
            ],
            tasks=tasks,
            process=Process.sequential,
            memory=False,   # context flows via task context=[] chain; memory=True requires OpenAI embeddings
            verbose=True,   # flip to False when promoting to production
            max_rpm=10,     # rate-limit MCP calls — critical for ZoomInfo credits
        )

        return crew.kickoff()

    def run(
        self,
        accounts: List[Dict[str, Any]],
        vertical: str,
        dry_run: bool = True,
        enrollment_enabled: bool = False,
        reply_inbox: str = "mike.madsen@leandata.com",
    ) -> Dict[str, Any]:
        """
        Run the AI SDR batch for a list of accounts.

        One crew.kickoff() per account — a failure on one account never stops
        the rest of the batch. Failed accounts go to the skipped list.

        Args:
            accounts: List of {"account_name": str, "salesforce_id": str}
            vertical: "fintech" | "insurance" | "smb" | "emea"
            dry_run: True = produce output JSON, make zero external writes
            enrollment_enabled: False = write to review_queue only (v1 default)

        Returns:
            Dict with results, skipped, and run metadata
        """
        # Guard: sequence must be configured before any enrollment can run
        sequence_id = SEQUENCE_IDS.get(vertical)
        if sequence_id is None and enrollment_enabled:
            raise ValueError(
                f"No Outreach sequence configured for vertical '{vertical}'. "
                f"Set enrollment_enabled=False or configure SEQUENCE_IDS['{vertical}']."
            )

        # Validate vertical is known at all
        if vertical not in SEQUENCE_IDS:
            raise ValueError(
                f"Unknown vertical '{vertical}'. "
                f"Valid options: {list(SEQUENCE_IDS.keys())}"
            )

        qa_config = load_qa_config()
        logging_enabled = self._supabase_logging_enabled(qa_config)
        run_id = str(uuid.uuid4())
        started_at = datetime.now(timezone.utc)

        # Create agents once — reused across all accounts in the batch
        self._create_agents()

        results: List[Any] = []
        skipped: List[Dict[str, Any]] = []

        for account in accounts:
            account_name = account.get("account_name", "unknown")
            logger.info(f"[AI SDR] Starting: {account_name} ({vertical})")

            try:
                result = self._run_single_account(
                    account=account,
                    vertical=vertical,
                    dry_run=dry_run,
                    enrollment_enabled=enrollment_enabled,
                    qa_config=qa_config,
                    sequence_id=sequence_id,
                )
                results.append(result)
                logger.info(f"[AI SDR] Completed: {account_name}")

                if logging_enabled:
                    self._log_account_result(run_id, account, vertical, result, sequence_id)

            except Exception as e:
                logger.error(f"[AI SDR] Failed on '{account_name}': {e}")
                skipped.append({
                    "account_name": account_name,
                    "salesforce_id": account.get("salesforce_id"),
                    "skip_reason": f"crew_error: {str(e)}",
                    "skipped_at": datetime.now(timezone.utc).isoformat(),
                })
                continue

        completed_at = datetime.now(timezone.utc)
        if logging_enabled:
            self._log_batch_run(
                run_id=run_id,
                started_at=started_at,
                completed_at=completed_at,
                vertical=vertical,
                total=len(accounts),
                processed=len(results),
                skipped_count=len(skipped),
                enrollment_enabled=enrollment_enabled,
                dry_run=dry_run,
            )

        return {
            "results": results,
            "skipped": skipped,
            "total_accounts": len(accounts),
            "processed": len(results),
            "skipped_count": len(skipped),
            "vertical": vertical,
            "dry_run": dry_run,
            "enrollment_enabled": enrollment_enabled,
            "sequence_id": sequence_id,
            "reply_inbox": reply_inbox,
        }
