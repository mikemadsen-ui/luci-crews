"""
Unit tests for JSON extractor utility.
"""

import pytest
from luci_crews.utils.json_extractor import extract_json_from_llm_response, _try_repair_json


class TestExtractJsonFromLlmResponse:
    """Tests for extract_json_from_llm_response function."""

    def test_direct_json_object(self):
        """Parse valid JSON object directly."""
        response = '{"name": "test", "value": 123}'
        result = extract_json_from_llm_response(response)
        assert result == {"name": "test", "value": 123}

    def test_direct_json_array(self):
        """Parse valid JSON array and wrap in items key."""
        response = '[1, 2, 3]'
        result = extract_json_from_llm_response(response)
        assert result == {"items": [1, 2, 3]}

    def test_markdown_code_block_with_json(self):
        """Extract JSON from ```json ... ``` block."""
        response = '''Here's the analysis:
```json
{"status": "success", "score": 85}
```
Hope this helps!'''
        result = extract_json_from_llm_response(response)
        assert result == {"status": "success", "score": 85}

    def test_markdown_code_block_without_language(self):
        """Extract JSON from ``` ... ``` block without json tag."""
        response = '''```
{"data": "value"}
```'''
        result = extract_json_from_llm_response(response)
        assert result == {"data": "value"}

    def test_embedded_json_in_text(self):
        """Extract JSON object embedded in prose."""
        response = '''Based on my analysis, the result is:
{"analysis": "complete", "findings": ["a", "b"]}
Let me know if you need more details.'''
        result = extract_json_from_llm_response(response)
        assert result["analysis"] == "complete"
        assert result["findings"] == ["a", "b"]

    def test_empty_response(self):
        """Handle empty response."""
        assert extract_json_from_llm_response("") == {}
        assert extract_json_from_llm_response(None) == {}

    def test_empty_response_with_default(self):
        """Use custom default for empty response."""
        default = {"status": "empty"}
        assert extract_json_from_llm_response("", default) == default

    def test_non_json_response_returns_text(self):
        """Non-JSON response returns text wrapper."""
        response = "This is just plain text without any JSON"
        result = extract_json_from_llm_response(response)
        assert "text" in result
        assert "plain text" in result["text"]

    def test_non_json_response_with_default(self):
        """Non-JSON response returns custom default."""
        response = "Plain text"
        default = {"error": "no json"}
        result = extract_json_from_llm_response(response, default)
        assert result == default

    def test_nested_json(self):
        """Handle nested JSON structures."""
        response = '{"outer": {"inner": {"deep": "value"}}}'
        result = extract_json_from_llm_response(response)
        assert result["outer"]["inner"]["deep"] == "value"

    def test_json_with_special_characters(self):
        """Handle JSON with newlines and special characters."""
        response = '{"text": "line1\\nline2", "path": "C:\\\\Users"}'
        result = extract_json_from_llm_response(response)
        assert result["text"] == "line1\nline2"
        assert result["path"] == "C:\\Users"

    def test_long_response_truncation(self):
        """Long non-JSON text is truncated in fallback."""
        long_text = "x" * 3000
        result = extract_json_from_llm_response(long_text)
        assert len(result["text"]) == 2000

    def test_array_in_code_block(self):
        """Extract array from code block."""
        response = '''```json
["item1", "item2", "item3"]
```'''
        result = extract_json_from_llm_response(response)
        assert result == {"items": ["item1", "item2", "item3"]}


class TestTryRepairJson:
    """Tests for _try_repair_json function."""

    def test_remove_trailing_comma_before_brace(self):
        """Remove trailing comma before closing brace."""
        malformed = '{"a": 1, "b": 2,}'
        repaired = _try_repair_json(malformed)
        assert repaired == '{"a": 1, "b": 2}'

    def test_remove_trailing_comma_before_bracket(self):
        """Remove trailing comma before closing bracket."""
        malformed = '["a", "b",]'
        repaired = _try_repair_json(malformed)
        assert repaired == '["a", "b"]'

    def test_fix_unquoted_keys(self):
        """Quote unquoted keys."""
        malformed = '{name: "test", value: 123}'
        repaired = _try_repair_json(malformed)
        assert '"name"' in repaired
        assert '"value"' in repaired

    def test_no_repair_needed(self):
        """Return None when no repair is needed."""
        valid = '{"valid": "json"}'
        assert _try_repair_json(valid) is None

    def test_complex_repair(self):
        """Repair multiple issues."""
        malformed = '{name: "test", items: [1, 2,],}'
        repaired = _try_repair_json(malformed)
        # Should fix both unquoted keys and trailing commas
        assert '"name"' in repaired
        assert '"items"' in repaired
