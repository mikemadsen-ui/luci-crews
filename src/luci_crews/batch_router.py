"""
Batch Processing Router for Overnight Sync Jobs

Provides FastAPI endpoints for triggering and monitoring overnight batch processing
that pre-syncs Avoma transcriptions and embeddings for all accounts.
"""

import os
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .batch_processor import OvernightBatchProcessor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/batch", tags=["batch"])

# In-memory status tracking (for real-time progress during processing)
batch_statuses: Dict[str, Dict[str, Any]] = {}


class OvernightSyncRequest(BaseModel):
    """Request model for overnight sync batch processing."""
    batchId: str
    batchSize: int = 10  # Process accounts in batches of 10
    totalAccounts: int
    triggeredBy: str = "cron"  # 'cron' or 'manual'


class BatchStatusResponse(BaseModel):
    """Response model for batch status queries."""
    batchId: str
    status: str
    accountsTotal: int
    accountsProcessed: int
    transcriptionsSynced: int
    embeddingsGenerated: int
    embeddingsSkipped: int
    errors: List[str]
    startedAt: Optional[str] = None
    completedAt: Optional[str] = None


def verify_cron_secret(secret: Optional[str]) -> bool:
    """Verify the cron secret matches the expected value."""
    expected = os.getenv("CRON_SECRET")
    if not expected:
        logger.warning("CRON_SECRET not configured - batch endpoints are unprotected")
        return True  # Allow if not configured (dev mode)
    return secret == expected


async def sync_transcriptions_via_nextjs() -> Optional[Dict[str, Any]]:
    """
    Call the Next.js batch-transcriptions endpoint to sync transcriptions.

    This endpoint handles both CRM-based and domain-based discovery.

    Returns:
        Dict with sync results or None if failed
    """
    import httpx

    nextjs_url = os.getenv("NEXTJS_APP_URL", "https://luci-app.vercel.app")
    cron_secret = os.getenv("CRON_SECRET")

    if not nextjs_url:
        logger.error("NEXTJS_APP_URL not configured")
        return None

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{nextjs_url}/api/cron/batch-transcriptions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {cron_secret}" if cron_secret else "",
                },
                json={
                    "method": "both",  # Run both CRM and domain-based sync
                    "limit": 50,  # Process more accounts in batch mode
                    "monthsBack": 6,
                },
                timeout=180.0,  # 3 minute timeout for batch sync
            )

            if response.status_code == 200:
                data = response.json()
                return data.get("data", data)
            else:
                logger.error(f"Transcription sync failed: {response.status_code} - {response.text[:200]}")
                return None

    except Exception as e:
        logger.error(f"Error calling transcription sync: {e}")
        return None


@router.post("/overnight-sync")
async def overnight_sync(
    request: OvernightSyncRequest,
    background_tasks: BackgroundTasks,
    x_internal_cron_secret: Optional[str] = Header(None),
):
    """
    Trigger overnight batch processing for all accounts.

    Processes accounts in batches of 10 to avoid overwhelming APIs.
    This endpoint returns immediately after accepting the request.
    Processing happens in the background.

    Args:
        request: Contains batchId, batchSize, and totalAccounts
        background_tasks: FastAPI background tasks handler
        x_internal_cron_secret: Secret header for authentication

    Returns:
        Acceptance confirmation with batch ID
    """
    # Verify authentication
    if not verify_cron_secret(x_internal_cron_secret):
        raise HTTPException(status_code=401, detail="Unauthorized")

    logger.info(f"Received overnight sync request: batch={request.batchId}, accounts={request.totalAccounts}")

    # Check if batch is already running
    if request.batchId in batch_statuses and batch_statuses[request.batchId].get("status") == "running":
        logger.warning(f"Batch {request.batchId} is already running")
        return JSONResponse(
            status_code=409,
            content={"status": "already_running", "batchId": request.batchId}
        )

    # Initialize status tracking
    batch_statuses[request.batchId] = {
        "status": "running",
        "accountsTotal": request.totalAccounts,
        "accountsProcessed": 0,
        "transcriptionsSynced": 0,
        "embeddingsGenerated": 0,
        "embeddingsSkipped": 0,
        "errors": [],
        "startedAt": datetime.utcnow().isoformat(),
        "completedAt": None,
    }

    # Add background task to process the batch
    background_tasks.add_task(
        run_batch_processing,
        request.batchId,
        request.batchSize,
        request.triggeredBy
    )

    return {
        "status": "accepted",
        "batchId": request.batchId,
        "accountsTotal": request.totalAccounts,
        "batchSize": request.batchSize,
        "message": "Batch processing started in background"
    }


@router.get("/status/{batch_id}")
async def get_batch_status(
    batch_id: str,
    x_internal_cron_secret: Optional[str] = Header(None),
):
    """
    Get the current status of a batch processing job.

    Args:
        batch_id: The unique batch identifier
        x_internal_cron_secret: Secret header for authentication

    Returns:
        Current status and progress of the batch
    """
    # Check in-memory status first (for running batches)
    if batch_id in batch_statuses:
        status = batch_statuses[batch_id]
        return BatchStatusResponse(
            batchId=batch_id,
            status=status.get("status", "unknown"),
            accountsTotal=status.get("accountsTotal", 0),
            accountsProcessed=status.get("accountsProcessed", 0),
            transcriptionsSynced=status.get("transcriptionsSynced", 0),
            embeddingsGenerated=status.get("embeddingsGenerated", 0),
            embeddingsSkipped=status.get("embeddingsSkipped", 0),
            errors=status.get("errors", []),
            startedAt=status.get("startedAt"),
            completedAt=status.get("completedAt"),
        )

    # Check database for completed batches
    try:
        from supabase import create_client
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

        if supabase_url and supabase_key:
            supabase = create_client(supabase_url, supabase_key)
            result = supabase.table("batch_processing_runs").select("*").eq("batch_id", batch_id).single().execute()

            if result.data:
                data = result.data
                return BatchStatusResponse(
                    batchId=batch_id,
                    status=data.get("status", "unknown"),
                    accountsTotal=data.get("accounts_total", data.get("users_total", 0)),
                    accountsProcessed=data.get("accounts_synced", 0),
                    transcriptionsSynced=data.get("transcriptions_synced", 0),
                    embeddingsGenerated=data.get("embeddings_generated", 0),
                    embeddingsSkipped=data.get("embeddings_skipped", 0),
                    errors=data.get("errors", []),
                    startedAt=data.get("started_at"),
                    completedAt=data.get("completed_at"),
                )
    except Exception as e:
        logger.error(f"Error fetching batch status from database: {e}")

    raise HTTPException(status_code=404, detail=f"Batch {batch_id} not found")


@router.get("/recent")
async def get_recent_batches(
    limit: int = 10,
    x_internal_cron_secret: Optional[str] = Header(None),
):
    """
    Get recent batch processing runs.

    Args:
        limit: Maximum number of batches to return (default 10)
        x_internal_cron_secret: Secret header for authentication

    Returns:
        List of recent batch runs with status
    """
    try:
        from supabase import create_client
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

        if not supabase_url or not supabase_key:
            return {"batches": [], "error": "Supabase not configured"}

        supabase = create_client(supabase_url, supabase_key)
        result = supabase.table("batch_processing_runs").select("*").order(
            "started_at", desc=True
        ).limit(limit).execute()

        batches = []
        for data in (result.data or []):
            batches.append({
                "batchId": data.get("batch_id"),
                "batchType": data.get("batch_type"),
                "status": data.get("status"),
                "accountsTotal": data.get("accounts_total", data.get("users_total", 0)),
                "accountsSynced": data.get("accounts_synced", 0),
                "transcriptionsSynced": data.get("transcriptions_synced", 0),
                "embeddingsGenerated": data.get("embeddings_generated", 0),
                "triggeredBy": data.get("triggered_by"),
                "startedAt": data.get("started_at"),
                "completedAt": data.get("completed_at"),
                "errorCount": len(data.get("errors", [])),
            })

        return {"batches": batches}

    except Exception as e:
        logger.error(f"Error fetching recent batches: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def run_batch_processing(
    batch_id: str,
    batch_size: int,
    triggered_by: str
):
    """
    Main batch processing function that runs in the background.

    Step 1: Call Next.js batch-transcriptions to sync ALL transcriptions (CRM + domain-based)
    Step 2: Generate embeddings for accounts that need them

    Args:
        batch_id: Unique identifier for this batch run
        batch_size: Number of accounts to process at a time
        triggered_by: 'cron' or 'manual'
    """
    status = batch_statuses[batch_id]
    processor = OvernightBatchProcessor()

    try:
        # Step 1: Sync transcriptions via Next.js unified endpoint
        logger.info(f"Batch {batch_id}: Starting transcription sync via Next.js...")
        transcription_result = await sync_transcriptions_via_nextjs()

        if transcription_result:
            status["transcriptionsSynced"] = transcription_result.get("totalTranscriptionsSynced", 0)
            logger.info(f"Batch {batch_id}: Transcription sync complete - {status['transcriptionsSynced']} synced")
        else:
            logger.warning(f"Batch {batch_id}: Transcription sync returned no result")

        # Step 2: Fetch accounts needing embeddings (may include newly synced transcriptions)
        accounts = await processor.fetch_accounts_needing_embeddings()
        status["accountsTotal"] = len(accounts)

        if len(accounts) == 0:
            logger.info(f"Batch {batch_id}: No accounts need processing")
            status["status"] = "completed"
            status["completedAt"] = datetime.utcnow().isoformat()
            await processor.init_batch_record(batch_id, 0, triggered_by)
            await processor.complete_batch(batch_id, "completed", [])
            return

        # Initialize database record
        await processor.init_batch_record(batch_id, len(accounts), triggered_by)

        # Process accounts in batches
        for i in range(0, len(accounts), batch_size):
            batch = accounts[i:i + batch_size]
            logger.info(f"Processing batch {i // batch_size + 1}: accounts {i} to {i + len(batch)}")

            for account in batch:
                try:
                    result = await processor.process_account(
                        account_id=account.get("id"),
                        salesforce_account_id=account.get("salesforce_id"),
                        account_name=account.get("name"),
                        batch_id=batch_id,
                    )

                    # Update progress
                    status["accountsProcessed"] += 1
                    status["transcriptionsSynced"] += result.get("transcriptions", 0)
                    status["embeddingsGenerated"] += result.get("embeddings", 0)
                    status["embeddingsSkipped"] += result.get("skipped", 0)

                except Exception as e:
                    error_msg = f"Account {account.get('name', account.get('id'))}: {str(e)}"
                    logger.error(f"Error processing account: {error_msg}")
                    status["errors"].append(error_msg)
                    status["accountsProcessed"] += 1

            # Update database progress after each batch
            await processor.update_batch_progress(
                batch_id=batch_id,
                accounts_processed=status["accountsProcessed"],
                accounts_total=status["accountsTotal"],
                transcriptions_synced=status["transcriptionsSynced"],
                embeddings_generated=status["embeddingsGenerated"],
                embeddings_skipped=status["embeddingsSkipped"],
            )

            logger.info(
                f"Batch progress: {status['accountsProcessed']}/{status['accountsTotal']} accounts, "
                f"{status['transcriptionsSynced']} transcriptions, "
                f"{status['embeddingsGenerated']} embeddings"
            )

        # Mark batch as complete
        final_status = "completed" if not status["errors"] else "partial"
        status["status"] = final_status
        status["completedAt"] = datetime.utcnow().isoformat()

        await processor.complete_batch(
            batch_id=batch_id,
            status=final_status,
            errors=status["errors"],
        )

        logger.info(
            f"Batch {batch_id} completed: "
            f"{status['accountsProcessed']}/{status['accountsTotal']} accounts, "
            f"{status['transcriptionsSynced']} transcriptions, "
            f"{status['embeddingsGenerated']} embeddings, "
            f"{len(status['errors'])} errors"
        )

    except Exception as e:
        logger.error(f"Batch {batch_id} failed: {e}")
        status["status"] = "failed"
        status["errors"].append(str(e))
        status["completedAt"] = datetime.utcnow().isoformat()

        await processor.complete_batch(
            batch_id=batch_id,
            status="failed",
            errors=status["errors"],
        )
