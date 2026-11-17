import base64
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import anthropic
import httpx

from utils import anthropic_utils as backend
from utils.llm_backend_utils import call_llm_with_contents, call_llm_with_images, call_llm_with_pdf, call_llm_with_text_prompt
from utils.response_parsing import parse_json_results, parse_latex_results, parse_json_latex_response


def sse_response(text, stop_reason="end_turn"):
    events = [
        {"type": "message_start", "message": {"id": "msg_test", "type": "message", "role": "assistant", "model": backend.DEFAULT_MODEL, "content": [], "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 10, "output_tokens": 0}}},
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": text}},
        {"type": "content_block_stop", "index": 0},
        {"type": "message_delta", "delta": {"stop_reason": stop_reason, "stop_sequence": None}, "usage": {"output_tokens": 20}},
        {"type": "message_stop"},
    ]
    return httpx.Response(200, headers={"content-type": "text/event-stream", "request-id": "req_test"}, content="".join(
        f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events
    ))


class MockClaude(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.requests = []
        self.text = '{"ok": true}'
        self.stop = "end_turn"
        def handler(request):
            self.requests.append(json.loads(request.content))
            return sse_response(self.text, self.stop)
        self.client = anthropic.Anthropic(
            api_key="test-key-never-real", base_url="https://claude.invalid",
            http_client=httpx.Client(transport=httpx.MockTransport(handler)), max_retries=0,
        )
        self.addCleanup(self.client.close)
        self.patcher = patch.object(backend, "_client", self.client)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.environment = patch.dict(os.environ, {
            "PAPER_ORCHESTRA_USAGE_LOG": str(self.root / "usage.jsonl"),
            "ANTHROPIC_TEMPERATURE": "", "ANTHROPIC_MAX_TOKENS": "16384",
            "ANTHROPIC_PRICE_INPUT_PER_MILLION": "4", "ANTHROPIC_PRICE_OUTPUT_PER_MILLION": "20",
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_text_sdk_contract(self):
        result = call_llm_with_text_prompt("hello", generation_configs={"system_instruction": "writer", "temperature": 0.7})
        self.assertEqual(result["parsed_response"], {"ok": True})
        body = self.requests[0]
        self.assertEqual(body["system"], "writer")
        self.assertEqual(body["model"], backend.DEFAULT_MODEL)
        self.assertEqual(body["messages"][0]["content"], [{"type": "text", "text": "hello"}])
        self.assertTrue(body["stream"])
        self.assertEqual(result["request_id"], "req_test")
        self.assertNotIn("temperature", body)
        self.assertAlmostEqual(result["cost_usd"], 0.00044)
        record = (self.root / "usage.jsonl").read_text()
        self.assertNotIn("test-key", record)
        self.assertNotIn("hello", record)

    def test_pdf_document_encoding(self):
        path = self.root / "paper.pdf"
        path.write_bytes(b"%PDF-test")
        call_llm_with_pdf(path, "review")
        part = self.requests[0]["messages"][0]["content"][0]
        self.assertEqual(part["type"], "document")
        self.assertEqual(base64.b64decode(part["source"]["data"]), b"%PDF-test")

    def test_jpeg_media_type_is_preserved(self):
        path = self.root / "figure.jpg"
        path.write_bytes(b"jpeg-placeholder")
        call_llm_with_images("see figure", [path])
        part = self.requests[0]["messages"][0]["content"][1]
        self.assertEqual(part["source"]["media_type"], "image/jpeg")

    def test_raw_latex_response(self):
        self.text = "```latex\n\\section{Results}\n```"
        result = call_llm_with_text_prompt("write", result_parsing_func=parse_latex_results)
        self.assertEqual(result["parsed_response"], "\\section{Results}")

    def test_truncation_is_rejected_and_billed(self):
        self.stop = "max_tokens"
        with self.assertRaisesRegex(ValueError, "incomplete"):
            call_llm_with_text_prompt("write")
        self.assertEqual(len(self.requests), 1)
        self.assertIn("max_tokens", (self.root / "usage.jsonl").read_text())

    def test_invalid_json_is_not_retried(self):
        self.text = "not JSON"
        with self.assertRaisesRegex(ValueError, "format"):
            call_llm_with_text_prompt("write")
        self.assertEqual(len(self.requests), 1)
        self.assertTrue((self.root / "usage.jsonl").exists())

    def test_raw_mode(self):
        self.text = "plain output"
        result = call_llm_with_text_prompt("write", return_json=False)
        self.assertEqual(result["parsed_response"], "plain output")

    def test_unsupported_model_is_rejected_before_request(self):
        with self.assertRaisesRegex(ValueError, "Claude only"):
            call_llm_with_text_prompt("hi", model_name="gemini-test")
        self.assertEqual(self.requests, [])

    def test_unknown_generation_option_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            call_llm_with_text_prompt("hi", generation_configs={"tools": ["google-search"]})
        self.assertEqual(self.requests, [])

    def test_invalid_prices_fail_before_a_paid_call(self):
        with patch.dict(os.environ, {"ANTHROPIC_PRICE_INPUT_PER_MILLION": "nan"}):
            with self.assertRaisesRegex(ValueError, "finite"):
                call_llm_with_text_prompt("hi")
        self.assertEqual(self.requests, [])

    def test_input_configuration_is_unchanged(self):
        config = {"system_instruction": "writer", "temperature": 0.3}
        call_llm_with_text_prompt("hi", generation_configs=config)
        self.assertEqual(config, {"system_instruction": "writer", "temperature": 0.3})

    def test_empty_input_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "empty"):
            call_llm_with_contents([""])
        self.assertEqual(self.requests, [])

    def test_auth_failure_is_not_retried(self):
        def handler(request):
            self.requests.append(json.loads(request.content))
            return httpx.Response(401, json={"type": "error", "error": {"type": "authentication_error", "message": "invalid test credential"}})
        with patch.object(backend, "_client", anthropic.Anthropic(
            api_key="test", http_client=httpx.Client(transport=httpx.MockTransport(handler)), max_retries=0,
        )):
            with self.assertRaises(anthropic.AuthenticationError):
                call_llm_with_text_prompt("hi")
        self.assertEqual(len(self.requests), 1)


class Parsers(unittest.TestCase):
    def test_fenced_json(self):
        self.assertEqual(parse_json_results('notes\n```json\n{"x": 1}\n```'), {"x": 1})

    def test_json_array(self):
        self.assertEqual(parse_json_results('[1, 2]'), [1, 2])

    def test_json_does_not_repair_invalid_scientific_text(self):
        self.assertIsNone(parse_json_results('{"x": "bad\\q"}'))

    def test_mixed_refinement_output(self):
        value = json.loads(parse_json_latex_response('```json\n{"edit": "ok"}\n```\n```latex\ntext\n```'))
        self.assertEqual(value, {"json": {"edit": "ok"}, "latex": "text"})

    def test_missing_refinement_latex_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_json_latex_response('```json\n{}\n```')


if __name__ == "__main__":
    unittest.main()
