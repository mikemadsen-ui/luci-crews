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
                "model": "text-embedding-3-small",
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

    def _ensure_supabase(self):
        """Ensure Supabase client is initialized."""
        if self.supabase is None:
            self.supabase = get_supabase_client()

    async def _load_avoma_config(self):
        """Load Avoma configuration from database."""
        if self.avoma_api_key:
            return  # Already loaded

        self._ensure_supabase()

        result = self.supabase.table("avoma_configs").select("*").eq(
            "is_active", True
        ).limit(1).execute()

        if result.data and len(result.data) > 0:
            config = result.data[0]
            self.avoma_api_key = config.get("api_key")
            self.avoma_base_url = config.get("api_url", "https://api.avoma.com")
            logger.info("Loaded Avoma configuration")
        else:
            logger.warning("No active Avoma configuration found")

    async def fetch_all_accounts(self) -> List[Dict[str, Any]]:
        """
        Fetch all accounts from the database.

        Returns:
            List of account dictionaries with id, salesforce_id, and name
        """
        self._ensure_supabase()

        # Fetch accounts in batches to avoid memory issues
        all_accounts = []
        page_size = 1000
        offset = 0

        while True:
            result = self.supabase.table("accounts").select(
                "id, salesforce_id, name"
            ).range(offset, offset + page_size - 1).execute()

            if not result.data:
                break

            all_accounts.extend(result.data)

            if len(result.data) < page_size:
                break

            offset += page_size

        logger.info(f"Fetched {len(all_accounts)} accounts for batch processing")
        return all_accounts

    async def init_batch_record(self, batch_id: str, accounts_total: int, triggered_by: str):
        """
        Initialize a batch processing record in the database.

        Args:
            batch_id: Unique batch identifier
            accounts_total: Total number of accounts to process
            triggered_by: 'cron' or 'manual'
        """
        self._ensure_supabase()

        try:
            self.supabase.table("batch_processing_runs").insert({
                "batch_id": batch_id,
                "batch_type": "overnight_sync",
                "status": "running",
                "users_total": accounts_total,  # Reusing field for accounts
                "triggered_by": triggered_by,
                "started_at": datetime.utcnow().isoformat(),
            }).execute()
            logger.info(f"Created batch record: {batch_id}")
        except Exception as e:
            logger.error(f"Error creating batch record: {e}")

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

        try:
            self.supabase.table("batch_processing_runs").update({
                "users_processed": accounts_processed,  # Reusing field
                "users_total": accounts_total,  # Reusing field
                "accounts_synced": accounts_processed,
                "transcriptions_synced": transcriptions_synced,
                "embeddings_generated": embeddings_generated,
                "embeddings_skipped": embeddings_skipped,
            }).eq("batch_id", batch_id).execute()
        except Exception as e:
            logger.error(f"Error updating batch progress: {e}")

    async def complete_batch(self, batch_id: str, status: str, errors: List[str]):
        """Mark a batch as complete in the database."""
        self._ensure_supabase()

        try:
            self.supabase.table("batch_processing_runs").update({
                "status": status,
                "completed_at": datetime.utcnow().isoformat(),
                "errors": errors,
            }).eq("batch_id", batch_id).execute()
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
        Process a single account: sync transcriptions and generate embeddings.

        Args:
            account_id: The account's UUID
            salesforce_account_id: The account's Salesforce ID
            account_name: The account name (for logging)
            batch_id: The batch ID for logging

        Returns:
            Dict with counts: transcriptions, embeddings, skipped
        """
        result = {"transcriptions": 0, "embeddings": 0, "skipped": 0}

        self._ensure_supabase()
        await self._load_avoma_config()

        logger.info(f"Processing account: {account_name} (SF ID: {salesforce_account_id})")

        # 1. Sync Avoma transcriptions for this account
        if self.avoma_api_key and salesforce_account_id:
            transcripts_synced = await self._sync_avoma_transcriptions(
                salesforce_account_id, account_name
            )
            result["transcriptions"] = transcripts_synced

        # 2. Generate embeddings for new transcriptions
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

        existing_map = {e["source_id"]: e for e in (existing_embeddings.data or [])}

        for transcript in transcriptions.data:
            meeting_uuid = transcript.get("avoma_meeting_uuid")
            text = transcript.get("transcription_text") or ""

            if not text.strip():
                continue

            # Check if embedding already exists and is up to date
            existing = existing_map.get(meeting_uuid)
            if existing:
                try:
                    existing_created = datetime.fromisoformat(
                        existing["created_at"].replace("Z", "+00:00")
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

                # Check if this exact content already exists
                hash_check = self.supabase.table("account_embeddings").select("id").eq(
                    "account_id", account_id
                ).eq("data_type", "transcription").eq("content_hash", content_hash).execute()

                if hash_check.data:
                    result["skipped"] += 1
                    continue

                try:
                    # Generate embedding
                    embedding = await generate_openai_embedding(chunk, self.openai_key)

                    # Store embedding
                    self.supabase.table("account_embeddings").insert({
                        "account_id": account_id,
                        "salesforce_account_id": salesforce_account_id,
                        "data_type": "transcription",
                        "source_id": meeting_uuid,
                        "content": chunk,
                        "content_hash": content_hash,
                        "embedding": embedding,
                        "metadata": {
                            "meetingSubject": transcript.get("meeting_subject"),
                            "meetingDate": transcript.get("meeting_date"),
                            "chunkIndex": i,
                            "totalChunks": len(chunks),
                        },
                    }).execute()

                    result["generated"] += 1

                    # Rate limiting for OpenAI
                    await asyncio.sleep(0.05)

                except Exception as e:
                    logger.error(f"Error generating embedding for chunk: {e}")

        return result
