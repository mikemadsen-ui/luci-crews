"""
SSE (Server-Sent Events) streaming utilities for crew execution.

This module provides reusable streaming response helpers for FastAPI endpoints
that run CrewAI crews with real-time progress updates.
"""

import json
import asyncio
import queue
import logging
from datetime import datetime
from typing import Any, Callable, Dict, Generator, Optional, TypeVar
from concurrent.futures import ThreadPoolExecutor

from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)


def sse_message(event_type: str, data: Dict[str, Any]) -> str:
    """Format a message as an SSE event."""
    return f"data: {json.dumps({'type': event_type, **data})}\n\n"


def sse_progress(stage: str, message: str) -> str:
    """Format a progress update as an SSE event."""
    return sse_message('progress', {'stage': stage, 'message': message})


def sse_result(result: Dict[str, Any], **extra_fields) -> str:
    """Format a result as an SSE event."""
    return sse_message('result', {'result': result, **extra_fields})


def sse_error(message: str) -> str:
    """Format an error as an SSE event."""
    return sse_message('error', {'message': message})


def sse_keepalive() -> str:
    """Return an SSE keepalive comment."""
    return ": keepalive\n\n"


def create_streaming_response(generator: Generator) -> StreamingResponse:
    """Create a StreamingResponse with standard SSE headers."""
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )


class SimpleStreamingContext:
    """
    Simple streaming context for crews that run synchronously.

    Collects progress messages during crew.run() and sends them all
    after the crew completes. Best for quick-running crews.

    Usage:
        ctx = SimpleStreamingContext()

        async def generate():
            yield ctx.init_message("Starting analysis...")

            result = crew.run(step_callback=ctx.step_callback)

            for msg in ctx.get_progress_messages():
                yield msg

            yield ctx.result_message(result)

        return create_streaming_response(generate())
    """

    def __init__(self):
        self.progress_messages: list[str] = []
        self.start_time = datetime.utcnow()

    def step_callback(self, message: str) -> None:
        """Callback to collect progress messages."""
        self.progress_messages.append(message)

    def init_message(self, message: str = "Starting analysis...") -> str:
        """Return the initial progress message."""
        return sse_progress('init', message)

    def get_progress_messages(self) -> list[str]:
        """Return all collected progress messages as SSE events."""
        return [sse_progress('processing', msg) for msg in self.progress_messages]

    def result_message(self, result: Dict[str, Any], **extra_fields) -> str:
        """Return the result as an SSE event."""
        return sse_result(result, **extra_fields)

    def error_message(self, error: str) -> str:
        """Return an error as an SSE event."""
        return sse_error(error)

    @property
    def execution_time(self) -> float:
        """Return the execution time in seconds."""
        return (datetime.utcnow() - self.start_time).total_seconds()


class ThreadedStreamingContext:
    """
    Threaded streaming context for crews that need real-time progress.

    Runs the crew in a thread pool executor while streaming progress
    messages in real-time. Best for long-running crews.

    Usage:
        ctx = ThreadedStreamingContext()

        async def generate():
            yield ctx.init_message("Starting analysis...")

            async for msg in ctx.run_with_progress(
                lambda step_cb: crew.run(step_callback=step_cb)
            ):
                yield msg

            if ctx.error:
                yield ctx.error_message(ctx.error)
            elif ctx.result:
                yield ctx.result_message(ctx.result)

        return create_streaming_response(generate())
    """

    def __init__(self, keepalive_interval: float = 5.0):
        self.progress_queue: queue.Queue = queue.Queue()
        self.result: Optional[Dict[str, Any]] = None
        self.error: Optional[str] = None
        self.done: bool = False
        self.start_time = datetime.utcnow()
        self.keepalive_interval = keepalive_interval

    def step_callback(self, message: str) -> None:
        """Thread-safe callback to send progress messages."""
        self.progress_queue.put({"type": "progress", "message": message})

    def init_message(self, message: str = "Starting analysis...") -> str:
        """Return the initial progress message."""
        return sse_progress('init', message)

    async def run_with_progress(
        self,
        crew_fn: Callable[[Callable[[str], None]], Dict[str, Any]],
        executor: Optional[ThreadPoolExecutor] = None
    ) -> Generator[str, None, None]:
        """
        Run the crew function in a thread and yield progress messages.

        Args:
            crew_fn: A callable that takes a step_callback and returns the result.
            executor: Optional ThreadPoolExecutor. Creates one if not provided.

        Yields:
            SSE formatted progress messages.
        """
        use_own_executor = executor is None
        if use_own_executor:
            executor = ThreadPoolExecutor(max_workers=1)

        def run_crew():
            try:
                self.result = crew_fn(self.step_callback)
            except Exception as e:
                logger.error(f"Crew execution error: {str(e)}")
                self.error = str(e)
            finally:
                self.done = True

        try:
            # Start the crew in a background thread
            future = executor.submit(run_crew)

            # Stream progress while crew is running
            while not self.done:
                try:
                    # Check for progress messages with timeout
                    msg = self.progress_queue.get(timeout=0.1)
                    if msg and msg.get("type") == "progress":
                        yield sse_progress('processing', msg.get("message", ""))
                except queue.Empty:
                    pass

                # Send keepalive periodically
                if not self.done:
                    await asyncio.sleep(0.1)
                    # TODO: Implement actual keepalive interval tracking

            # Drain any remaining progress messages
            while True:
                try:
                    msg = self.progress_queue.get_nowait()
                    if msg and msg.get("type") == "progress":
                        yield sse_progress('processing', msg.get("message", ""))
                except queue.Empty:
                    break

        finally:
            if use_own_executor:
                executor.shutdown(wait=False)

    def result_message(self, result: Optional[Dict[str, Any]] = None, **extra_fields) -> str:
        """Return the result as an SSE event."""
        return sse_result(result or self.result or {}, **extra_fields)

    def error_message(self, error: Optional[str] = None) -> str:
        """Return an error as an SSE event."""
        return sse_error(error or self.error or "Unknown error")

    @property
    def execution_time(self) -> float:
        """Return the execution time in seconds."""
        return (datetime.utcnow() - self.start_time).total_seconds()


# Backward compatibility exports
def format_sse_progress(stage: str, message: str) -> str:
    """Deprecated: Use sse_progress instead."""
    return sse_progress(stage, message)


def format_sse_result(result: Dict[str, Any], **extra_fields) -> str:
    """Deprecated: Use sse_result instead."""
    return sse_result(result, **extra_fields)


def format_sse_error(message: str) -> str:
    """Deprecated: Use sse_error instead."""
    return sse_error(message)
