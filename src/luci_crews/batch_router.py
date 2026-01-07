"""
Batch Processing Router for Overnight Sync Jobs

Provides FastAPI endpoints for triggering and monitoring overnight batch processing
that pre-syncs accounts, Avoma transcriptions, and embeddings for active CSM users.
"""

import os
import json
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .batch_processor import OvernightBatchProcessor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/batch", tags=["batch"])

# In-memory status tracking (for real-time progress during processing)
batch_statuses: Dict[str, Dict[str, Any]] = {}


class UserDetail(BaseModel):
    """Details about a user to process in the batch."""
    id: str
    email: str
    salesforceUserId: Optional[str] = None


class OvernightSyncRequest(BaseModel):
    """Request model for overnight sync batch processing."""
    batchId: str
    activeUserIds: List[str]
    userDetails: List[UserDetail]
    triggeredBy: str = "cron"  # 'cron' or 'manual'


class BatchStatusResponse(BaseModel):
    """Response model for batch status queries."""
    batchId: str
    status: str
    usersTotal: int
    usersProcessed: int
    accountsSynced: int
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


@router.post("/overnight-sync")
async def overnight_sync(
    request: OvernightSyncRequest,
    background_tasks: BackgroundTasks,
    x_internal_cron_secret: Optional[str] = Header(None),
):
    """
    Trigger overnight batch processing for active CSM users.

    This endpoint returns immediately after accepting the request.
    Processing happens in the background.

    Args:
        request: Contains batchId, list of user IDs, and user details
        background_tasks: FastAPI background tasks handler
        x_internal_cron_secret: Secret header for authentication

    Returns:
        Acceptance confirmation with batch ID
    """
    # Verify authentication
    if not verify_cron_secret(x_internal_cron_secret):
        raise HTTPException(status_code=401, detail="Unauthorized")

    logger.info(f"Received overnight sync request: batch={request.batchId}, users={len(request.userDetails)}")

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
        "usersTotal": len(request.userDetails),
        "usersProcessed": 0,
        "accountsSynced": 0,
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
        request.userDetails,
        request.triggeredBy
    )

    return {
        "status": "accepted",
        "batchId": request.batchId,
        "usersQueued": len(request.userDetails),
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
            usersTotal=status.get("usersTotal", 0),
            usersProcessed=status.get("usersProcessed", 0),
            accountsSynced=status.get("accountsSynced", 0),
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
                    usersTotal=data.get("users_total", 0),
                    usersProcessed=data.get("users_processed", 0),
                    accountsSynced=data.get("accounts_synced", 0),
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
                "usersTotal": data.get("users_total", 0),
                "usersProcessed": data.get("users_processed", 0),
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
    users: List[UserDetail],
    triggered_by: str
):
    """
    Main batch processing function that runs in the background.

    Processes each user sequentially to avoid overwhelming external APIs.
    Updates progress in both in-memory status and database.

    Args:
        batch_id: Unique identifier for this batch run
        users: List of users to process
        triggered_by: 'cron' or 'manual'
    """
    status = batch_statuses[batch_id]
    processor = OvernightBatchProcessor()

    try:
        # Initialize database record
        await processor.init_batch_record(batch_id, len(users), triggered_by)

        # Process each user
        for user in users:
            try:
                result = await processor.process_user(
                    user_id=user.id,
                    user_email=user.email,
                    salesforce_user_id=user.salesforceUserId,
                    batch_id=batch_id,
                )

                # Update progress
                status["usersProcessed"] += 1
                status["accountsSynced"] += result.get("accounts", 0)
                status["transcriptionsSynced"] += result.get("transcriptions", 0)
                status["embeddingsGenerated"] += result.get("embeddings", 0)
                status["embeddingsSkipped"] += result.get("skipped", 0)

                # Update database progress
                await processor.update_batch_progress(
                    batch_id=batch_id,
                    users_processed=status["usersProcessed"],
                    accounts_synced=status["accountsSynced"],
                    transcriptions_synced=status["transcriptionsSynced"],
                    embeddings_generated=status["embeddingsGenerated"],
                    embeddings_skipped=status["embeddingsSkipped"],
                )

                logger.info(
                    f"Processed user {user.email}: "
                    f"{result.get('accounts', 0)} accounts, "
                    f"{result.get('transcriptions', 0)} transcriptions, "
                    f"{result.get('embeddings', 0)} embeddings"
                )

            except Exception as e:
                error_msg = f"User {user.email}: {str(e)}"
                logger.error(f"Error processing user: {error_msg}")
                status["errors"].append(error_msg)

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
            f"{status['usersProcessed']}/{status['usersTotal']} users, "
            f"{status['accountsSynced']} accounts, "
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
