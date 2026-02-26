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

    # Try 3b: Handle truncated JSON (LLM hit max_tokens before closing braces)
    # Look for JSON that starts with { but doesn't have matching }
    if '{' in result_str:
        truncated_repair = _try_repair_truncated_json(result_str)
        if truncated_repair:
            try:
                return json.loads(truncated_repair)
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
    # Log both start and end to help diagnose truncation issues
    preview_start = result_str[:300] if len(result_str) > 300 else result_str
    preview_end = result_str[-200:] if len(result_str) > 200 else ""
    logger.warning(
        f"Failed to extract JSON from LLM response (len={len(result_str)}). "
        f"Start: {preview_start!r}... End: ...{preview_end!r}"
    )
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


def _try_repair_truncated_json(text: str) -> Optional[str]:
    """
    Attempt to repair JSON truncated by max_tokens limit.

    When LLMs hit token limits, JSON often ends mid-value like:
    {"key": "value", "other": "incomple

    Strategy: Find positions of complete JSON values, truncate there, then close brackets.

    Args:
        text: Text containing potentially truncated JSON

    Returns:
        Repaired JSON string, or None if repair wasn't possible
    """
    # Find start of JSON
    start_idx = text.find('{')
    if start_idx == -1:
        return None

    json_text = text[start_idx:]

    # Find all positions where we have a complete value
    # These are safe truncation points: after "string", after }, after ], after numbers, after true/false/null
    safe_positions = []
    i = 0
    in_string = False
    escape_next = False

    while i < len(json_text):
        char = json_text[i]

        if escape_next:
            escape_next = False
            i += 1
            continue

        if char == '\\' and in_string:
            escape_next = True
            i += 1
            continue

        if char == '"':
            if in_string:
                # End of string - safe position
                safe_positions.append(i + 1)
            in_string = not in_string
            i += 1
            continue

        if in_string:
            i += 1
            continue

        # Outside string
        if char in '}]':
            safe_positions.append(i + 1)
        elif char == ',':
            # After comma is safe if previous was a complete value
            if safe_positions and safe_positions[-1] == i:
                safe_positions[-1] = i + 1  # Include the comma

        i += 1

    if not safe_positions:
        return None

    # Try each safe position from the end until we get valid JSON
    for pos in reversed(safe_positions):
        candidate = json_text[:pos].rstrip().rstrip(',')

        # Count unclosed brackets
        stack = []
        in_str = False
        esc = False
        for c in candidate:
            if esc:
                esc = False
                continue
            if c == '\\' and in_str:
                esc = True
                continue
            if c == '"':
                in_str = not in_str
                continue
            if in_str:
                continue
            if c == '{':
                stack.append('}')
            elif c == '[':
                stack.append(']')
            elif c in '}]' and stack and stack[-1] == c:
                stack.pop()

        if not stack:
            continue  # Already complete, not truncated

        # Close the brackets
        repaired = candidate + ''.join(reversed(stack))

        # Verify it parses
        try:
            json.loads(repaired)
            logger.info(f"Repaired truncated JSON: closed {len(stack)} bracket(s) at position {pos}")
            return repaired
        except json.JSONDecodeError:
            continue

    return None
