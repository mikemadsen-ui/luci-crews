"""
AI SDR crew endpoint.

POST /api/crew/ai-sdr

Batch job that researches prospect accounts, finds ICP contacts, drafts
personalized 4-step Outreach sequences, runs QA, and gates enrollment
behind human review.

Defaults: dry_run=True, enrollment_enabled=False.
The crew never touches Outreach unless both flags are explicitly overridden.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from ..models import AiSdrRequest
from ..crews.ai_sdr_crew import AiSdrCrew, SEQUENCE_IDS

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/crew", tags=["ai-sdr"])


@router.post("/ai-sdr")
async def run_ai_sdr_crew(request: AiSdrRequest):
    """
    Run the AI SDR batch crew against a list of prospect accounts.

    For each account the crew:
      1. Validates against Salesforce (skip existing customers + open opps)
      2. Builds relationship network via graph_account_network
      3. Enriches with ZoomInfo firmographics and finds ICP contact
      4. Surfaces LUCI signals and checks for prior LeanData meetings
      5. Drafts personalized email + all 4 Outreach sequence steps
      6. Runs QA — scores confidence, flags bad records
      7. Gates enrollment behind human_input=True (crew level) and
         Step 1 manual task in Outreach (sequence level)

    Defaults: dry_run=True, enrollment_enabled=False.
    One failed account never stops the rest of the batch.
    """
    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc).isoformat()

    logger.info(
        f"[AI SDR] Starting run_id={run_id} vertical={request.vertical} "
        f"accounts={len(request.accounts)} dry_run={request.dryRun} "
        f"enrollment_enabled={request.enrollmentEnabled}"
    )

    # Validate vertical before spending any MCP credits
    if request.vertical not in SEQUENCE_IDS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unknown vertical '{request.vertical}'. "
                f"Valid options: {list(SEQUENCE_IDS.keys())}"
            ),
        )

    sequence_id = SEQUENCE_IDS.get(request.vertical)
    if sequence_id is None and request.enrollmentEnabled:
        raise HTTPException(
            status_code=400,
            detail=(
                f"No Outreach sequence configured for vertical '{request.vertical}'. "
                f"Set enrollment_enabled=False or configure the sequence first."
            ),
        )

    try:
        crew = AiSdrCrew(user_id=request.userId)

        # Convert Pydantic account objects to plain dicts for the crew
        accounts_payload = [
            {"account_name": a.account_name, "salesforce_id": a.salesforce_id}
            for a in request.accounts
        ]

        # crew.run() is synchronous (crew.kickoff() blocks) — offload to thread pool
        result = await asyncio.to_thread(
            crew.run,
            accounts=accounts_payload,
            vertical=request.vertical,
            dry_run=request.dryRun,
            enrollment_enabled=request.enrollmentEnabled,
            reply_inbox=request.replyInbox,
        )

        completed_at = datetime.now(timezone.utc).isoformat()
        logger.info(
            f"[AI SDR] Completed run_id={run_id} "
            f"processed={result['processed']} skipped={result['skipped_count']}"
        )

        return {
            "run_id": run_id,
            "started_at": started_at,
            "completed_at": completed_at,
            "vertical": request.vertical,
            "sequence_id": sequence_id,
            "dry_run": result["dry_run"],
            "enrollment_enabled": result["enrollment_enabled"],
            "total_accounts": result["total_accounts"],
            "processed": result["processed"],
            "skipped_count": result["skipped_count"],
            "results": result["results"],
            "skipped": result["skipped"],
        }

    except ValueError as e:
        # Catches guard errors propagated from crew.run()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[AI SDR] run_id={run_id} failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
