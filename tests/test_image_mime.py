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

"""Tests that image payloads declare the real MIME type of the bytes.

The plotting agent writes .jpg figures, the demo and raw_materials folders can
hold .png figures, and both LLM backends used to declare a single hardcoded
type. These tests need no API keys and no network access.
"""

import base64
import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from utils.common_utils import get_image_mime_type

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 32
GIF_BYTES = b"GIF89a" + b"\x00" * 32
WEBP_BYTES = b"RIFF\x24\x00\x00\x00WEBP" + b"\x00" * 32


def _write(tmp_path, name, data):
    path = tmp_path / name
    path.write_bytes(data)
    return str(path)


@pytest.mark.parametrize(
    "name,data,expected",
    [
        ("figure.png", PNG_BYTES, "image/png"),
        ("figure.jpg", JPEG_BYTES, "image/jpeg"),
        ("figure.jpeg", JPEG_BYTES, "image/jpeg"),
        ("figure.gif", GIF_BYTES, "image/gif"),
        ("figure.webp", WEBP_BYTES, "image/webp"),
    ],
)
def test_detects_format_from_signature(tmp_path, name, data, expected):
    assert get_image_mime_type(_write(tmp_path, name, data)) == expected


def test_trusts_bytes_over_a_wrong_extension(tmp_path):
    # A PNG whose name claims to be a JPEG: the bytes win.
    path = _write(tmp_path, "plot.jpg", PNG_BYTES)
    assert get_image_mime_type(path) == "image/png"


def test_detects_format_without_any_extension(tmp_path):
    path = _write(tmp_path, "figure_without_extension", JPEG_BYTES)
    assert get_image_mime_type(path) == "image/jpeg"


def test_falls_back_to_extension_when_bytes_are_not_recognised(tmp_path):
    path = _write(tmp_path, "figure.png", b"not an image")
    assert get_image_mime_type(path) == "image/png"


def test_unknown_content_returns_octet_stream(tmp_path):
    path = _write(tmp_path, "figure.bin", b"not an image")
    assert get_image_mime_type(path) == "application/octet-stream"


def test_missing_file_returns_octet_stream(tmp_path):
    path = str(tmp_path / "does_not_exist.png")
    assert get_image_mime_type(path) == "application/octet-stream"


def test_openai_payload_declares_png_for_png_bytes(tmp_path):
    pytest.importorskip("openai")
    pytest.importorskip("cv2")
    from utils.openai_utils import get_openai_image_part_from_path

    path = _write(tmp_path, "figure.png", PNG_BYTES)
    part = get_openai_image_part_from_path(path)
    url = part[0]["image_url"]["url"]

    assert url.startswith("data:image/png;base64,")
    assert base64.b64decode(url.split(",", 1)[1]) == PNG_BYTES


def test_openai_payload_declares_jpeg_for_jpeg_bytes(tmp_path):
    pytest.importorskip("openai")
    pytest.importorskip("cv2")
    from utils.openai_utils import get_openai_image_part_from_path

    path = _write(tmp_path, "figure.jpg", JPEG_BYTES)
    url = get_openai_image_part_from_path(path)[0]["image_url"]["url"]

    assert url.startswith("data:image/jpeg;base64,")


def test_gemini_parts_declare_the_real_mime_type(tmp_path, monkeypatch):
    pytest.importorskip("google.genai")
    from utils import gemini_utils

    captured = {}

    def fake_call_with_contents(**kwargs):
        captured["contents"] = kwargs["contents"]
        return {"raw_response": "{}", "parsed_response": {}}

    monkeypatch.setattr(
        gemini_utils, "call_gemini_with_contents", fake_call_with_contents
    )

    # The plotting agent writes .jpg; raw_materials figures are usually .png.
    jpg_path = _write(tmp_path, "plot.jpg", JPEG_BYTES)
    png_path = _write(tmp_path, "uploaded.png", PNG_BYTES)

    gemini_utils.call_gemini_with_images(
        prompt="describe the figures",
        images=[jpg_path, png_path],
        model_name="gemini-3.1-pro-preview",
        check_parsed_response_not_none=False,
    )

    image_parts = captured["contents"][1:]  # first part is the text prompt
    assert [part.inline_data.mime_type for part in image_parts] == [
        "image/jpeg",
        "image/png",
    ]
    assert image_parts[0].inline_data.data == JPEG_BYTES
    assert image_parts[1].inline_data.data == PNG_BYTES
