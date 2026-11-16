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

"""Stage markers that let an interrupted run continue at the first unfinished stage."""

import hashlib
import json
import os

STAGES = ("outline", "literature", "sections", "refinement")


def hash_paths(paths):
    """Hash file names and bytes of files and directories (sorted, deterministic)."""
    digest = hashlib.sha256()
    for path in paths:
        files = []
        if os.path.isdir(path):
            for root, _, names in os.walk(path):
                files += [os.path.join(root, name) for name in names]
        elif os.path.isfile(path):
            files.append(path)
        for file in sorted(files):
            digest.update(os.path.relpath(file, os.path.dirname(path)).encode())
            with open(file, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    digest.update(chunk)
    return digest.hexdigest()


def stage_key(previous_key, *values):
    """A stage is reusable only if its inputs and all earlier stages are unchanged."""
    digest = hashlib.sha256(previous_key.encode())
    for value in values:
        digest.update(b"\0" + str(value).encode())
    return digest.hexdigest()


class ResumeState:
    """Markers are always written; they are read (and stages skipped) only if enabled."""

    def __init__(self, base_dir, enabled=False):
        self.path = os.path.join(base_dir, ".resume.json")
        self.enabled = enabled
        self.data = {}
        if enabled and os.path.exists(self.path):
            try:
                with open(self.path, encoding="utf-8") as f:
                    self.data = json.load(f)
            except (OSError, ValueError):
                self.data = {}

    def _save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)
        os.replace(tmp, self.path)

    def is_done(self, stage, key, outputs):
        return (
            self.enabled
            and self.data.get(stage) == key
            and all(os.path.exists(p) for p in outputs)
        )

    def begin(self, stage):
        """Running a stage invalidates it and every later stage."""
        for later in STAGES[STAGES.index(stage) :]:
            self.data.pop(later, None)
        self._save()

    def done(self, stage, key):
        self.data[stage] = key
        self._save()
