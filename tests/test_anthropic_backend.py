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

"""Tests of the Anthropic backend with a fake client: no network, no credentials."""

import base64
from types import SimpleNamespace

import pytest

from utils import anthropic_utils, llm_backend_utils
from utils.anthropic_utils import (
    AnthropicRefusalError,
    build_anthropic_request,
    call_anthropic_with_content,
    call_anthropic_with_text_prompt,
    get_anthropic_image_part_from_path,
    get_anthropic_pdf_part_from_path,
    text_of_message,
)

REVIEW = 'THOUGHT:\nsolid paper.\n\nREVIEW JSON:\n```json\n{"Overall": 6, "Decision": "Accept"}\n```'


def message(text: str = REVIEW, stop_reason: str = "end_turn", thinking: bool = True) -> SimpleNamespace:
    blocks = [SimpleNamespace(type="thinking", thinking="")] if thinking else []
    blocks.append(SimpleNamespace(type="text", text=text))
    return SimpleNamespace(content=blocks, stop_reason=stop_reason, stop_details=SimpleNamespace(category="cyber"))


class FakeStream:
    def __init__(self, final: SimpleNamespace):
        self.final = final

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self) -> SimpleNamespace:
        return self.final


class FakeAnthropicClient:
    """Stands in for anthropic.Anthropic: records each request and replays the queued responses."""

    def __init__(self, responses: list):
        self.responses = list(responses)
        self.requests = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))

    def _stream(self, **request) -> FakeStream:
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return FakeStream(response)


def test_request_carries_system_prompt_effort_and_no_sampling_parameters():
    request = build_anthropic_request(
        [{"type": "text", "text": "hi"}],
        "claude-haiku-5-5",
        {"temperature": 0.75, "system_instruction": "ignored here", "effort": "low", "max_tokens": 2000},
        system_prompt="You are a reviewer.",
    )
    assert request == {
        "model": "claude-haiku-5-5",
        "max_tokens": 2000,
        "messages": [{"role": "user", "content": [{"type": "text", "text": "hi"}]}],
        "system": "You are a reviewer.",
        "output_config": {"effort": "low"},
    }


def test_request_enables_refusal_fallback_only_on_models_that_support_it():
    with_fallback = build_anthropic_request([], "claude-opus-5-5")
    assert with_fallback["betas"] == ["server-side-fallback-2026-07-01"]
    assert with_fallback["fallbacks"] == "default"
    assert with_fallback["max_tokens"] == 64000
    without = build_anthropic_request([], "claude-haiku-5-5")
    assert "betas" not in without and "fallbacks" not in without


def test_text_prompt_returns_raw_text_and_parsed_json_skipping_thinking_blocks():
    client = FakeAnthropicClient([message()])
    out = call_anthropic_with_text_prompt("review this", "claude-opus-5-5", system_prompt="sys", client=client)
    assert out == {"raw_response": REVIEW, "parsed_response": {"Overall": 6, "Decision": "Accept"}}
    assert client.requests[0]["messages"] == [{"role": "user", "content": [{"type": "text", "text": "review this"}]}]
    assert client.requests[0]["system"] == "sys"


def test_unparseable_response_is_retried_and_then_succeeds():
    client = FakeAnthropicClient([message("no json here"), message()])
    out = call_anthropic_with_content([{"type": "text", "text": "x"}], "claude-opus-5-5", client=client)
    assert out["parsed_response"] == {"Overall": 6, "Decision": "Accept"}
    assert len(client.requests) == 2


def test_unparseable_response_raises_after_the_last_attempt():
    client = FakeAnthropicClient([message("no json here")])
    with pytest.raises(AssertionError, match="Parsed response is None"):
        call_anthropic_with_content([{"type": "text", "text": "x"}], "claude-opus-5-5", max_retries=1, client=client)


def test_refusal_raises_without_retrying():
    client = FakeAnthropicClient([message(stop_reason="refusal"), message()])
    with pytest.raises(AnthropicRefusalError, match="cyber"):
        call_anthropic_with_content([{"type": "text", "text": "x"}], "claude-opus-5-5", client=client)
    assert len(client.requests) == 1


def test_truncated_response_is_an_error_not_a_partial_answer():
    with pytest.raises(ValueError, match="max_tokens"):
        text_of_message(message(stop_reason="max_tokens"))


def test_image_part_uses_the_media_type_of_the_file(tmp_path):
    png = tmp_path / "figure.png"
    png.write_bytes(b"\x89PNG fake")
    (part,) = get_anthropic_image_part_from_path(str(png))
    assert part["type"] == "image"
    assert part["source"]["media_type"] == "image/png"
    assert base64.standard_b64decode(part["source"]["data"]) == b"\x89PNG fake"
    with pytest.raises(ValueError, match="Unsupported image type"):
        get_anthropic_image_part_from_path(str(tmp_path / "figure.tiff"))


def test_pdf_part_is_a_base64_document_block_and_rejects_oversized_files(tmp_path, monkeypatch):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.7 fake")
    (part,) = get_anthropic_pdf_part_from_path(str(pdf))
    assert part["type"] == "document"
    assert part["source"]["media_type"] == "application/pdf"
    assert base64.standard_b64decode(part["source"]["data"]) == b"%PDF-1.7 fake"
    monkeypatch.setattr(anthropic_utils, "PDF_MAX_BYTES", 4)
    with pytest.raises(ValueError, match="accepts PDFs up to 4"):
        get_anthropic_pdf_part_from_path(str(pdf))


def test_router_sends_claude_models_to_the_anthropic_backend(tmp_path, monkeypatch):
    client = FakeAnthropicClient([message(), message(), message("plain text")])
    monkeypatch.setattr(anthropic_utils, "_anthropic_client", client)
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.7 fake")
    png = tmp_path / "figure.png"
    png.write_bytes(b"\x89PNG fake")

    text = llm_backend_utils.call_llm_with_text_prompt(
        "p", "claude-opus-5-5", generation_configs={"temperature": 0.75, "system_instruction": "sys"}
    )
    with_pdf = llm_backend_utils.call_llm_with_pdf(str(pdf), "p", "claude-opus-5-5", system_instruction="sys2")
    with_image = llm_backend_utils.call_llm_with_images("p", [str(png)], "claude-opus-5-5", return_json=False)

    assert text["parsed_response"] == with_pdf["parsed_response"] == {"Overall": 6, "Decision": "Accept"}
    assert with_image["parsed_response"] == "plain text"
    text_request, pdf_request, image_request = client.requests
    assert text_request["system"] == "sys" and "temperature" not in text_request
    assert [b["type"] for b in pdf_request["messages"][0]["content"]] == ["document", "text"]
    assert pdf_request["system"] == "sys2"
    assert [b["type"] for b in image_request["messages"][0]["content"]] == ["image", "text"]
