"""
JSON extraction utility for parsing LLM responses.

Consolidates the duplicate JSON extraction pattern found across 18+ crew files.
"""

import json
import logging
import re
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def extract_json_from_llm_response(
    response_text: str,
    default: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Extract JSON from LLM response text, handling common output formats.

    Handles:
    - Direct JSON (response is valid JSON)
    - Markdown code blocks (```json ... ``` or ``` ... ```)
    - Inline JSON objects ({ ... })
    - JSON arrays ([ ... ])

    Args:
        response_text: The raw text response from the LLM
        default: Default dict to return if parsing fails (default: {"text": response_text})

    Returns:
        Parsed JSON as a dictionary, or the default value if parsing fails
    """
    if not response_text:
        return default if default is not None else {}

    result_str = str(response_text).strip()

    # Try 1: Direct JSON parse (response is valid JSON)
    try:
        parsed = json.loads(result_str)
        if isinstance(parsed, dict):
            return parsed
        if isinstance(parsed, list):
            return {"items": parsed}
    except json.JSONDecodeError:
        pass

    # Try 2: Extract from markdown code blocks (```json ... ``` or ``` ... ```)
    code_block_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', result_str)
    if code_block_match:
        try:
            parsed = json.loads(code_block_match.group(1))
            if isinstance(parsed, dict):
                return parsed
            if isinstance(parsed, list):
                return {"items": parsed}
        except json.JSONDecodeError:
            pass

    # Try 3: Find JSON object in text (greedy match for outermost braces)
    brace_match = re.search(r'\{[\s\S]*\}', result_str)
    if brace_match:
        try:
            return json.loads(brace_match.group())
        except json.JSONDecodeError:
            # Try to repair common issues
            json_str = brace_match.group()
            repaired = _try_repair_json(json_str)
            if repaired:
                try:
                    return json.loads(repaired)
                except json.JSONDecodeError:
                    pass

    # Try 4: Find JSON array in text
    array_match = re.search(r'\[[\s\S]*\]', result_str)
    if array_match:
        try:
            parsed = json.loads(array_match.group())
            if isinstance(parsed, list):
                return {"items": parsed}
        except json.JSONDecodeError:
            pass

    # Fallback: return default or wrap text
    logger.warning("Failed to extract JSON from LLM response")
    if default is not None:
        return default
    return {"text": result_str[:2000] if len(result_str) > 2000 else result_str}


def _try_repair_json(json_str: str) -> Optional[str]:
    """
    Attempt to repair common JSON issues from LLM output.

    Args:
        json_str: Potentially malformed JSON string

    Returns:
        Repaired JSON string, or None if repair wasn't possible
    """
    repaired = json_str

    # Remove trailing commas before } or ]
    repaired = re.sub(r',\s*([}\]])', r'\1', repaired)

    # Fix unquoted keys (simple cases)
    repaired = re.sub(r'(\{|\,)\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'\1"\2":', repaired)

    if repaired != json_str:
        return repaired

    return None
