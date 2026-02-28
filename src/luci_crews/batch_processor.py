"""
Batch Processor for Overnight Sync Jobs

Handles the actual processing logic for pre-syncing:
1. Avoma transcriptions for all accounts
2. Embeddings (vectorization) for new transcriptions
"""

import os
import hashlib
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

import httpx

logger = logging.getLogger(__name__)


def get_supabase_client():
    """Get a Supabase client instance."""
    from supabase import create_client

    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    if not supabase_url or not supabase_key:
        raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")

    return create_client(supabase_url, supabase_key)


def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 100) -> List[str]:
    """
    Split text into overlapping chunks for embedding.

    Args:
        text: The text to chunk
        chunk_size: Maximum characters per chunk
        overlap: Number of characters to overlap between chunks

    Returns:
        List of text chunks
    """
    if not text or len(text) <= chunk_size:
        return [text] if text else []

    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size

        # Try to break at a sentence or word boundary
        if end < len(text):
            # Look for sentence boundary
            for sep in ['. ', '! ', '? ', '\n\n', '\n', ' ']:
                last_sep = text.rfind(sep, start + chunk_size // 2, end)
                if last_sep > start:
                    end = last_sep + len(sep)
                    break

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        start = end - overlap

    return chunks


async def generate_openai_embedding(text: str, api_key: str) -> List[float]:
    """
    Generate an embedding vector using OpenAI's API.

    Args:
        text: The text to embed
        api_key: OpenAI API key

    Returns:
        List of floats representing the embedding vector
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.openai.com/v1/embeddings",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
                "input": text[:8000],  # Truncate to avoid token limits
            },
            timeout=30.0,
        )

        if response.status_code != 200:
            raise Exception(f"OpenAI API error: {response.status_code} - {response.text}")

        data = response.json()
        return data["data"][0]["embedding"]


class OvernightBatchProcessor:
    """
    Processes overnight batch sync jobs for all accounts.

    Handles:
    - Fetching all accounts
    - Syncing Avoma transcriptions
    - Generating embeddings for new content
    """

    def __init__(self):
        self.supabase = None
        self.openai_key = os.getenv("OPENAI_API_KEY")
        self.avoma_base_url = None
        self.avoma_api_key = None

    async def __aenter__(self):
        """Async context manager entry - initializes Supabase client."""
        self._ensure_supabase()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - cleans up Supabase client."""
        await self.close()
        return False  # Don't suppress exceptions

    async def close(self):
        """Clean up resources, particularly the Supabase client connection."""
        if self.supabase is not None:
            # The Supabase Python client uses httpx under the hood.
            # Setting to None allows garbage collection to clean up.
            # If using auth, sign_out() should be called for proper cleanup.
            try:
                # Check if there's an auth session to clean up
                if hasattr(self.supabase, 'auth') and self.supabase.auth:
                    # Sign out to close any background connections
                    await asyncio.to_thread(self.supabase.auth.sign_out)
                    logger.debug("Supabase auth session signed out")
            except Exception as e:
                # Don't fail on cleanup errors, just log
                logger.debug(f"Supabase cleanup note: {e}")
            finally:
                self.supabase = None
                logger.debug("Supabase client reference cleared")

    def _ensure_supabase(self):
        """Ensure Supabase client is initialized."""
        if self.supabase is None:
            self.supabase = get_supabase_client()

    async def _load_avoma_config(self):
        """Load Avoma configuration from database."""
        if self.avoma_api_key:
            return  # Already loaded

        self._ensure_supabase()

        def _fetch():
            return self.supabase.table("avoma_configs").select("*").eq(
                "is_active", True
            ).limit(1).execute()

        result = await asyncio.to_thread(_fetch)

        if result.data and len(result.data) > 0:
            config = result.data[0]
            self.avoma_api_key = config.get("api_key")
            self.avoma_base_url = config.get("api_url", "https://api.avoma.com")
            logger.info("Loaded Avoma configuration")
        else:
            logger.warning("No active Avoma configuration found")

    async def fetch_accounts_needing_embeddings(self) -> List[Dict[str, Any]]:
        """
        Fetch accounts that have recent transcriptions but are missing embeddings.

        Only returns accounts where:
        1. Transcriptions exist from the last 90 days
        2. Those transcriptions don't have embeddings yet

        Returns:
            List of account dictionaries with id, salesforce_id, and name
        """
        self._ensure_supabase()

        # Get accounts with transcriptions in the last 90 days
        ninety_days_ago = (datetime.utcnow() - timedelta(days=90)).isoformat()

        # Step 1: Get salesforce_account_ids with recent transcriptions
        def _fetch_transcriptions():
            return self.supabase.table("transcriptions").select(
                "salesforce_account_id, avoma_meeting_uuid"
            ).gte("meeting_date", ninety_days_ago).execute()

        transcription_result = await asyncio.to_thread(_fetch_transcriptions)

        if not transcription_result.data:
            logger.info("No recent transcriptions found")
            return []

        # Build a map of salesforce_account_id -> list of meeting_uuids
        account_transcripts = {}
        for t in transcription_result.data:
            sf_id = t.get("salesforce_account_id")
            meeting_uuid = t.get("avoma_meeting_uuid")
            if sf_id and meeting_uuid:
                if sf_id not in account_transcripts:
                    account_transcripts[sf_id] = []
                account_transcripts[sf_id].append(meeting_uuid)

        if not account_transcripts:
            logger.info("No accounts with recent transcriptions")
            return []

        logger.info(f"Found {len(account_transcripts)} accounts with recent transcriptions")

        # Step 2: Get existing embeddings for these accounts
        sf_account_ids = list(account_transcripts.keys())

        # Query in batches to avoid URL length limits
        existing_embeddings = set()
        batch_size = 50
        for i in range(0, len(sf_account_ids), batch_size):
            batch_ids = sf_account_ids[i:i + batch_size]

            def _fetch_embeddings(ids=batch_ids):
                return self.supabase.table("account_embeddings").select(
                    "salesforce_account_id, source_id"
                ).in_("salesforce_account_id", ids).eq(
                    "data_type", "transcription"
                ).execute()

            embed_result = await asyncio.to_thread(_fetch_embeddings)

            for e in (embed_result.data or []):
                # Track which transcriptions already have embeddings
                key = f"{e.get('salesforce_account_id')}:{e.get('source_id')}"
                existing_embeddings.add(key)

        # Step 3: Find accounts with transcriptions missing embeddings
        accounts_needing_work = []
        for sf_id, meeting_uuids in account_transcripts.items():
            has_missing = False
            for uuid in meeting_uuids:
                key = f"{sf_id}:{uuid}"
                if key not in existing_embeddings:
                    has_missing = True
                    break

            if has_missing:
                accounts_needing_work.append(sf_id)

        if not accounts_needing_work:
            logger.info("All recent transcriptions already have embeddings")
            return []

        logger.info(f"Found {len(accounts_needing_work)} accounts needing embeddings")

        # Step 4: Get full account details for accounts needing work
        accounts = []
        for i in range(0, len(accounts_needing_work), batch_size):
            batch_ids = accounts_needing_work[i:i + batch_size]

            def _fetch_accounts(ids=batch_ids):
                return self.supabase.table("accounts").select(
                    "id, salesforce_id, name"
                ).in_("salesforce_id", ids).execute()

            account_result = await asyncio.to_thread(_fetch_accounts)
            accounts.extend(account_result.data or [])

        logger.info(f"Returning {len(accounts)} accounts for batch processing")
        return accounts

    async def init_batch_record(self, batch_id: str, accounts_total: int, triggered_by: str):
        """
        Initialize a batch processing record in the database.

        Args:
            batch_id: Unique batch identifier
            accounts_total: Total number of accounts to process
            triggered_by: 'cron' or 'manual'
        """
        self._ensure_supabase()

        logger.info(f"Creating batch record: batch_id={batch_id}, accounts_total={accounts_total}, triggered_by={triggered_by}")

        try:
            def _upsert():
                # Use upsert so retries don't fail on duplicate batch_id
                return self.supabase.table("batch_processing_runs").upsert({
                    "batch_id": batch_id,
                    "batch_type": "overnight_sync",
                    "status": "running",
                    "users_total": accounts_total,  # Reusing field for accounts
                    "triggered_by": triggered_by,
                    "started_at": datetime.utcnow().isoformat(),
                    # Reset progress on retry
                    "users_processed": 0,
                    "completed_at": None,
                    "error_message": None,
                }, on_conflict="batch_id").execute()

            result = await asyncio.to_thread(_upsert)

            if result.data:
                logger.info(f"Batch record created/updated successfully: {batch_id}")
            else:
                logger.warning(f"Batch record upsert returned no data: {batch_id}")
        except Exception as e:
            logger.error(f"Error creating batch record {batch_id}: {e}", exc_info=True)

    async def update_batch_progress(
        self,
        batch_id: str,
        accounts_processed: int,
        accounts_total: int,
        transcriptions_synced: int,
        embeddings_generated: int,
        embeddings_skipped: int,
    ):
        """Update batch progress in the database."""
        self._ensure_supabase()

        logger.info(f"Updating progress for batch {batch_id}: {accounts_processed}/{accounts_total} accounts, {embeddings_generated} embeddings")

        try:
            def _update():
                return self.supabase.table("batch_processing_runs").update({
                    "users_processed": accounts_processed,  # Reusing field
                    "users_total": accounts_total,  # Reusing field
                    "accounts_synced": accounts_processed,
                    "transcriptions_synced": transcriptions_synced,
                    "embeddings_generated": embeddings_generated,
                    "embeddings_skipped": embeddings_skipped,
                }).eq("batch_id", batch_id).execute()

            result = await asyncio.to_thread(_update)

            # Log result to diagnose update issues
            if result.data:
                logger.info(f"Batch progress updated: {len(result.data)} rows affected")
            else:
                logger.warning(f"Batch progress update returned no data - batch_id may not exist: {batch_id}")
        except Exception as e:
            logger.error(f"Error updating batch progress for {batch_id}: {e}", exc_info=True)

    async def complete_batch(self, batch_id: str, status: str, errors: List[str]):
        """Mark a batch as complete in the database."""
        self._ensure_supabase()

        try:
            def _complete():
                return self.supabase.table("batch_processing_runs").update({
                    "status": status,
                    "completed_at": datetime.utcnow().isoformat(),
                    "errors": errors,
                }).eq("batch_id", batch_id).execute()

            await asyncio.to_thread(_complete)
            logger.info(f"Batch {batch_id} marked as {status}")
        except Exception as e:
            logger.error(f"Error completing batch: {e}")

    async def process_account(
        self,
        account_id: str,
        salesforce_account_id: str,
        account_name: str,
        batch_id: str,
    ) -> Dict[str, int]:
        """
        Process a single account: generate embeddings for transcriptions.

        Note: Transcription sync is done upfront via Next.js batch-transcriptions endpoint,
        so this method only handles embedding generation.

        Args:
            account_id: The account's UUID
            salesforce_account_id: The account's Salesforce ID
            account_name: The account name (for logging)
            batch_id: The batch ID for logging

        Returns:
            Dict with counts: transcriptions (always 0), embeddings, skipped
        """
        result = {"transcriptions": 0, "embeddings": 0, "skipped": 0}

        self._ensure_supabase()

        logger.info(f"Generating embeddings for: {account_name} (SF ID: {salesforce_account_id})")

        # Generate embeddings for transcriptions (sync is done upfront via Next.js)
        if self.openai_key:
            embed_result = await self._generate_embeddings_for_account(
                account_id, salesforce_account_id
            )
            result["embeddings"] = embed_result.get("generated", 0)
            result["skipped"] = embed_result.get("skipped", 0)

        # Rate limiting delay between accounts
        await asyncio.sleep(0.1)

        return result

    async def _sync_avoma_transcriptions(
        self,
        salesforce_account_id: str,
        account_name: str,
    ) -> int:
        """
        Sync Avoma transcriptions for an account.

        Args:
            salesforce_account_id: The Salesforce account ID
            account_name: Account name for logging

        Returns:
            Number of transcriptions synced
        """
        if not self.avoma_api_key or not self.avoma_base_url:
            return 0

        synced_count = 0

        try:
            # Search for meetings associated with this account
            async with httpx.AsyncClient() as client:
                # Calculate date range (last 90 days)
                to_date = datetime.utcnow()
                from_date = to_date - timedelta(days=90)

                response = await client.get(
                    f"{self.avoma_base_url}/v1/meetings",
                    headers={
                        "Authorization": f"Bearer {self.avoma_api_key}",
                        "Content-Type": "application/json",
                    },
                    params={
                        "crm_account_ids": salesforce_account_id,
                        "from_date": from_date.strftime("%Y-%m-%d"),
                        "to_date": to_date.strftime("%Y-%m-%d"),
                        "page_size": 20,
                    },
                    timeout=30.0,
                )

                if response.status_code != 200:
                    logger.warning(f"Avoma search failed for {account_name}: {response.status_code}")
                    return 0

                data = response.json()
                meetings = data.get("results", data.get("meetings", []))

                for meeting in meetings:
                    meeting_uuid = meeting.get("uuid") or meeting.get("id")
                    if not meeting_uuid:
                        continue

                    # Check if we already have this transcription
                    existing = self.supabase.table("transcriptions").select("id").eq(
                        "avoma_meeting_uuid", meeting_uuid
                    ).execute()

                    if existing.data:
                        continue  # Already synced

                    # Check if transcript is ready
                    if not meeting.get("transcript_ready", False):
                        continue

                    # Fetch the transcript
                    transcript_response = await client.get(
                        f"{self.avoma_base_url}/v1/meetings/{meeting_uuid}/transcript",
                        headers={
                            "Authorization": f"Bearer {self.avoma_api_key}",
                            "Content-Type": "application/json",
                        },
                        timeout=60.0,
                    )

                    if transcript_response.status_code != 200:
                        continue

                    transcript_data = transcript_response.json()
                    transcript_text = transcript_data.get("text", transcript_data.get("transcript", ""))

                    if not transcript_text:
                        continue

                    # Save to database
                    self.supabase.table("transcriptions").upsert({
                        "avoma_meeting_uuid": meeting_uuid,
                        "salesforce_account_id": salesforce_account_id,
                        "transcription_text": transcript_text,
                        "speakers": transcript_data.get("speakers"),
                        "meeting_subject": meeting.get("subject", meeting.get("title")),
                        "meeting_date": meeting.get("start_at", meeting.get("start_time")),
                        "meeting_duration": meeting.get("duration"),
                        "meeting_url": meeting.get("url"),
                        "attendees": meeting.get("attendees"),
                        "last_synced_at": datetime.utcnow().isoformat(),
                    }, on_conflict="avoma_meeting_uuid").execute()

                    synced_count += 1

                    # Rate limiting
                    await asyncio.sleep(0.2)

        except Exception as e:
            logger.error(f"Error syncing Avoma for {account_name}: {e}")

        return synced_count

    async def _generate_embeddings_for_account(
        self,
        account_id: str,
        salesforce_account_id: str,
    ) -> Dict[str, int]:
        """
        Generate embeddings for transcriptions that don't have them yet.

        Args:
            account_id: The account's UUID
            salesforce_account_id: The account's Salesforce ID

        Returns:
            Dict with 'generated' and 'skipped' counts
        """
        result = {"generated": 0, "skipped": 0}

        if not self.openai_key:
            return result

        self._ensure_supabase()

        # Get transcriptions for this account
        transcriptions = self.supabase.table("transcriptions").select(
            "id, avoma_meeting_uuid, transcription_text, meeting_subject, meeting_date, updated_at"
        ).eq("salesforce_account_id", salesforce_account_id).order(
            "meeting_date", desc=True
        ).limit(20).execute()

        if not transcriptions.data:
            return result

        # Get existing embeddings for this account
        existing_embeddings = self.supabase.table("account_embeddings").select(
            "source_id, content_hash, created_at"
        ).eq("account_id", account_id).eq("data_type", "transcription").execute()

        # Build a map of meeting_uuid -> list of existing embeddings
        # source_id can be "meeting_uuid" or "meeting_uuid_chunk_N"
        existing_by_meeting = {}
        for e in (existing_embeddings.data or []):
            source_id = e["source_id"]
            # Extract the base meeting UUID (before "_chunk_" if present)
            if "_chunk_" in source_id:
                base_uuid = source_id.rsplit("_chunk_", 1)[0]
            else:
                base_uuid = source_id

            if base_uuid not in existing_by_meeting:
                existing_by_meeting[base_uuid] = []
            existing_by_meeting[base_uuid].append(e)

        for transcript in transcriptions.data:
            meeting_uuid = transcript.get("avoma_meeting_uuid")
            text = transcript.get("transcription_text") or ""

            if not text.strip():
                continue

            # Check if embedding already exists and is up to date
            existing_list = existing_by_meeting.get(meeting_uuid, [])
            if existing_list:
                try:
                    # Use the most recent embedding's created_at for comparison
                    most_recent = max(existing_list, key=lambda x: x["created_at"])
                    existing_created = datetime.fromisoformat(
                        most_recent["created_at"].replace("Z", "+00:00")
                    )
                    transcript_updated = datetime.fromisoformat(
                        transcript["updated_at"].replace("Z", "+00:00")
                    )

                    if existing_created >= transcript_updated:
                        result["skipped"] += 1
                        continue
                except Exception:
                    pass  # If date parsing fails, re-generate

            # Chunk the text
            chunks = chunk_text(text, chunk_size=1000, overlap=100)

            for i, chunk in enumerate(chunks[:30]):  # Max 30 chunks per transcript
                content_hash = hashlib.sha256(chunk.encode()).hexdigest()
                # Include chunk index in source_id to make each chunk unique
                # The unique constraint is on (source_id, data_type)
                chunk_source_id = f"{meeting_uuid}_chunk_{i}" if len(chunks) > 1 else meeting_uuid

                # Check if this chunk already exists by source_id (uses unique index, faster than content_hash)
                existing_check = self.supabase.table("account_embeddings").select("id").eq(
                    "source_id", chunk_source_id
                ).eq("data_type", "transcription").limit(1).execute()

                if existing_check.data:
                    result["skipped"] += 1
                    continue

                try:
                    # Generate embedding
                    embedding = await generate_openai_embedding(chunk, self.openai_key)

                    # Store embedding - use upsert to handle any remaining duplicates gracefully
                    self.supabase.table("account_embeddings").upsert({
                        "account_id": account_id,
                        "salesforce_account_id": salesforce_account_id,
                        "data_type": "transcription",
                        "source_id": chunk_source_id,
                        "content": chunk,
                        "content_hash": content_hash,
                        "embedding": embedding,
                        "metadata": {
                            "meetingSubject": transcript.get("meeting_subject"),
                            "meetingDate": transcript.get("meeting_date"),
                            "chunkIndex": i,
                            "totalChunks": len(chunks),
                            "originalMeetingUuid": meeting_uuid,
                        },
                    }, on_conflict="source_id,data_type").execute()

                    result["generated"] += 1

                    # Rate limiting for OpenAI
                    await asyncio.sleep(0.05)

                except Exception as e:
                    logger.error(f"Error generating embedding for chunk: {e}")

        return result
