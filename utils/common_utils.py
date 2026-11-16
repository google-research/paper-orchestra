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

import datetime
import os
import os.path as osp


def create_log_folder(
    prefix: str = "",
    date_str: str = "",
    log_dir: str = "./logs/paper_writing",
):
    now = datetime.datetime.now()
    timestamp_str = now.strftime("%Y_%m_%d_%H_%M_%S")

    log_dir_name = f"log_{timestamp_str}"
    if prefix != "":
        log_dir_name = f"{prefix}_" + log_dir_name

    if date_str == "":
        date_str = now.strftime("%Y%m%d")
    log_path = os.path.join(log_dir, date_str, log_dir_name)

    os.makedirs(log_path, exist_ok=True)

    print(f"Generated Log Directory Name: **{log_dir_name}**")
    print(f"Full Log Path: **{log_path}**")

    return log_path


def load_md_file(md_file_path: str):
    if not osp.exists(md_file_path):
        print(
            f"Error! Markdown file not found at '{md_file_path}', use empty string..."
        )
        return None

    with open(md_file_path, "r") as f:
        prompt_content = f.read()

    return prompt_content


# Magic bytes for the image formats the pipeline can produce or receive.
_IMAGE_MAGIC_SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
)

_IMAGE_EXTENSION_MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


def get_image_mime_type(image_path: str) -> str:
    """Returns the MIME type of an image file, e.g. "image/png".

    The file signature is checked before the extension because figures are
    either uploaded by users or written by the plotting agent, so the extension
    can disagree with the actual bytes. Returns "application/octet-stream" when
    the format cannot be determined, so callers never have to handle None.
    """
    try:
        with open(image_path, "rb") as f:
            header = f.read(12)
    except OSError:
        return "application/octet-stream"

    for signature, mime_type in _IMAGE_MAGIC_SIGNATURES:
        if header.startswith(signature):
            return mime_type

    if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "image/webp"

    extension = osp.splitext(image_path)[1].lower()
    return _IMAGE_EXTENSION_MIME_TYPES.get(extension, "application/octet-stream")
