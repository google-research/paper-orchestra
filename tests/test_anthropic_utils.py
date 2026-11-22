# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import unittest
from types import SimpleNamespace
from unittest import mock

import anthropic
import httpx2 as httpx
from google.genai import types

from utils import anthropic_utils as au
from utils import llm_backend_utils as lb


def _msg(text='{"a": 1}', stop_reason="end_turn", stop_details=None):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        stop_reason=stop_reason,
        stop_details=stop_details,
    )


class _StreamCM:
    def __init__(self, outcome):
        self.outcome = outcome

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_final_message(self):
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def _fake_client(outcomes):
    """outcomes: list of messages/exceptions consumed one per stream call."""
    outcomes = list(outcomes)

    def _stream(**kwargs):
        o = outcomes.pop(0) if len(outcomes) > 1 else outcomes[0]
        return _StreamCM(o)

    client = SimpleNamespace(
        messages=SimpleNamespace(stream=mock.Mock(side_effect=_stream)),
        beta=SimpleNamespace(
            messages=SimpleNamespace(stream=mock.Mock(side_effect=_stream))
        ),
    )
    return client


def _http_error(cls, status):
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    resp = httpx.Response(status, request=req)
    return cls("error", response=resp, body=None)


class ConversionTests(unittest.TestCase):
    def test_conversion(self):
        png = b"\x89PNG\r\n"
        pdf = b"%PDF-1.4"
        blocks = au.gemini_contents_to_claude_blocks(
            [
                "hello",
                types.Part.from_text(text="part"),
                types.Part.from_bytes(data=png, mime_type="image/png"),
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_bytes(data=pdf, mime_type="application/pdf"),
                        types.Part.from_text(text="end"),
                    ],
                ),
            ]
        )
        self.assertEqual([b["type"] for b in blocks], ["text", "text", "image", "document", "text"])
        self.assertEqual(blocks[0]["text"], "hello")
        self.assertEqual(blocks[2]["source"]["media_type"], "image/png")
        self.assertEqual(blocks[2]["source"]["data"], "iVBORw0K")
        self.assertEqual(blocks[3]["source"]["media_type"], "application/pdf")
        self.assertEqual(blocks[4]["text"], "end")

    def test_single_item(self):
        self.assertEqual(
            au.gemini_contents_to_claude_blocks("x"), [{"type": "text", "text": "x"}]
        )

    def test_unsupported_mime(self):
        with self.assertRaises(ValueError):
            au.gemini_contents_to_claude_blocks(
                types.Part.from_bytes(data=b"x", mime_type="audio/mp3")
            )

    def test_empty_part(self):
        with self.assertRaises(ValueError):
            au.gemini_contents_to_claude_blocks(types.Part())


class RequestKwargsTests(unittest.TestCase):
    def test_mapping_and_no_mutation(self):
        cfg = {"system_instruction": "sys", "temperature": 0.3, "top_p": 1, "top_k": 3}
        orig = dict(cfg)
        client = _fake_client([_msg()])
        with mock.patch.object(au, "get_anthropic_client", return_value=client):
            au.call_claude_with_text_prompt("hi", "claude-haiku-5-5", generation_configs=cfg)
        kw = client.messages.stream.call_args.kwargs
        self.assertEqual(kw["system"], "sys")
        self.assertEqual(kw["max_tokens"], 64000)
        for k in ("temperature", "top_p", "top_k", "thinking"):
            self.assertNotIn(k, kw)
        self.assertEqual(kw["messages"], [{"role": "user", "content": [{"type": "text", "text": "hi"}]}])
        self.assertEqual(cfg, orig)

    def test_max_output_tokens(self):
        kw = au._build_request_kwargs("claude-x", {"max_output_tokens": 100})
        self.assertEqual(kw["max_tokens"], 100)

    def test_unsupported_key_no_api_call(self):
        client = _fake_client([_msg()])
        with mock.patch.object(au, "get_anthropic_client", return_value=client):
            with self.assertRaises(au.ClaudeRequestError):
                au.call_claude_with_text_prompt(
                    "hi", "claude-haiku-5-5", generation_configs={"tools": []}
                )
        client.messages.stream.assert_not_called()
        client.beta.messages.stream.assert_not_called()


class CallTests(unittest.TestCase):
    def test_json_parsing(self):
        client = _fake_client([_msg('```json\n{"k": 2}\n```')])
        with mock.patch.object(au, "get_anthropic_client", return_value=client):
            res = au.call_claude_with_text_prompt("hi", "claude-haiku-5-5")
        self.assertEqual(res["parsed_response"], {"k": 2})
        self.assertIn("k", res["raw_response"])

    def test_refusal_not_retried(self):
        client = _fake_client([_msg("", "refusal", {"category": "x"})])
        with mock.patch.object(au, "get_anthropic_client", return_value=client):
            with self.assertRaises(au.ClaudeRequestError):
                au.call_claude_with_text_prompt("hi", "claude-haiku-5-5", result_parsing_func=lambda s: s)
        self.assertEqual(client.messages.stream.call_count, 1)

    def test_transient_retries(self):
        client = _fake_client([RuntimeError_free(), _msg()])
        with mock.patch.object(au, "get_anthropic_client", return_value=client), mock.patch.object(
            au.time, "sleep"
        ):
            res = au.call_claude_with_text_prompt("hi", "claude-haiku-5-5")
        self.assertEqual(res["parsed_response"], {"a": 1})
        self.assertEqual(client.messages.stream.call_count, 2)

    def test_bad_request_not_retried(self):
        client = _fake_client([_http_error(anthropic.BadRequestError, 400)])
        with mock.patch.object(au, "get_anthropic_client", return_value=client), mock.patch.object(
            au.time, "sleep"
        ):
            with self.assertRaises(anthropic.BadRequestError):
                au.call_claude_with_text_prompt("hi", "claude-haiku-5-5")
        self.assertEqual(client.messages.stream.call_count, 1)

    def test_missing_key(self):
        with mock.patch.object(au, "_anthropic_client", None), mock.patch.dict(
            au.os.environ, {}, clear=True
        ):
            with self.assertRaises(ValueError) as cm:
                au.get_anthropic_client()
        self.assertIn("ANTHROPIC_API_KEY", str(cm.exception))

    def test_fallback_branch(self):
        client = _fake_client([_msg()])
        with mock.patch.object(au, "get_anthropic_client", return_value=client):
            au.call_claude_with_text_prompt("hi", "claude-opus-5-5")
            kw = client.beta.messages.stream.call_args.kwargs
            self.assertEqual(kw["fallbacks"], "default")
            self.assertEqual(kw["betas"], ["server-side-fallback-2026-07-01"])
            client.messages.stream.assert_not_called()
            au.call_claude_with_text_prompt("hi", "claude-haiku-5-5")
            client.messages.stream.assert_called_once()
            self.assertEqual(client.beta.messages.stream.call_count, 1)


    def test_fallback_keeps_only_final_text(self):
        msg = SimpleNamespace(
            content=[
                SimpleNamespace(type="text", text="partial {"),
                SimpleNamespace(type="fallback"),
                SimpleNamespace(type="text", text='{"a": 1}'),
            ],
            stop_reason="end_turn",
            stop_details=None,
        )
        client = _fake_client([msg])
        with mock.patch.object(au, "get_anthropic_client", return_value=client):
            res = au.call_claude_with_text_prompt("hi", "claude-opus-5-5")
        self.assertEqual(res["raw_response"], '{"a": 1}')
        self.assertEqual(res["parsed_response"], {"a": 1})

    def test_parser_value_error_is_retried(self):
        client = _fake_client([_msg("bad"), _msg("good")])
        calls = []

        def parser(s):
            calls.append(s)
            if s == "bad":
                raise ValueError("unparseable")
            return s

        with mock.patch.object(au, "get_anthropic_client", return_value=client), mock.patch.object(
            au.time, "sleep"
        ):
            res = au.call_claude_with_text_prompt(
                "hi", "claude-haiku-5-5", result_parsing_func=parser
            )
        self.assertEqual(res["parsed_response"], "good")
        self.assertEqual(calls, ["bad", "good"])


def RuntimeError_free():
    return ConnectionError("transient")


class RouterTests(unittest.TestCase):
    NAMES = {
        "text": ("call_llm_with_text_prompt", ("hi",), "text_prompt"),
        "images": ("call_llm_with_images", ("hi", ["a.png"]), "images"),
        "pdf": ("call_llm_with_pdf", ("a.pdf", "hi"), "pdf"),
        "contents": ("call_llm_with_contents", (["hi"],), "contents"),
    }

    def _run(self, kind, model):
        fn_name, args, suffix = self.NAMES[kind]
        targets = {
            "claude": f"call_claude_with_{suffix}",
            "gemini": "call_gemini_with_contents" if kind == "pdf" else f"call_gemini_with_{suffix}",
            "openai": "call_openai_models_with_text_prompt",
        }
        mocks = {}
        patches = []
        for k, t in targets.items():
            m = mock.Mock(return_value={"raw_response": k, "parsed_response": k})
            mocks[k] = m
            patches.append(mock.patch.object(lb, t, m))
        # pdf/images for openai use extra helpers
        patches.append(mock.patch.object(lb, "load_paper", mock.Mock(return_value="t")))
        patches.append(
            mock.patch.object(lb, "get_openai_image_part_from_path", mock.Mock(return_value=[]))
        )
        patches.append(mock.patch.object(lb, "call_openai_models_with_content", mocks["openai"]))
        if kind == "pdf":
            patches.append(mock.patch("builtins.open", mock.mock_open(read_data=b"%PDF")))
        for p in patches:
            p.start()
        try:
            res = getattr(lb, fn_name)(*args, model_name=model)
        finally:
            for p in patches:
                p.stop()
        return res["raw_response"]

    def test_routing(self):
        for kind in self.NAMES:
            with self.subTest(kind=kind):
                self.assertEqual(self._run(kind, "claude-sonnet-5-5"), "claude")
                self.assertEqual(self._run(kind, "gemini-3.1-pro-preview"), "gemini")
                expected_gpt = "gemini" if kind == "contents" else "openai"
                self.assertEqual(self._run(kind, "gpt-5"), expected_gpt)


if __name__ == "__main__":
    unittest.main()
