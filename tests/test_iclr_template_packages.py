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

"""The ICLR 2025 template must supply the macros the writing agents are told to use.

`section_writing_agent_prompt` instructs the model to build tables with
`\\toprule`/`\\midrule`/`\\bottomrule` (booktabs) and the conference guidelines
tell it to include figures with `\\includegraphics` (graphicx), while also
telling it to keep the preamble unchanged.  A template that ships neither
package therefore cannot compile the LaTeX the pipeline produces.
"""

import base64
import os
import re
import shutil
import subprocess
import tempfile
import unittest

TEMPLATE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "templates",
    "iclr2025",
)
TEMPLATE_TEX = os.path.join(TEMPLATE_DIR, "template.tex")

# Body the section writing agent is instructed to emit, plus a figure so that
# \includegraphics has a real file to load.
BODY = r"""
\begin{figure}[t]
\centering
\includegraphics[width=0.8\linewidth]{figures/plot.jpg}
\caption{Example caption.}
\end{figure}

\begin{table}[t]
\caption{Example table.}
\centering
\begin{tabular}{lcc}
\toprule
Setting & Seen & Unseen \\
\midrule
Ours & 43.43 & 54.58 \\
\bottomrule
\end{tabular}
\end{table}
"""

PLACEHOLDER = "Experimental setup, results, and analysis here."

# 1x1 baseline JPEG, enough for \includegraphics to embed a real image.
JPEG_BYTES = base64.b64decode(
    "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0a"
    "HBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPDs0NDT/wAALCAABAAEBAREA/8QAFAABAAAAAAAA"
    "AAAAAAAAAAAACf/EABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAD8AKp//2Q=="
)


class IclrTemplatePackageTest(unittest.TestCase):
    def _template_source(self):
        with open(TEMPLATE_TEX, encoding="utf-8") as f:
            return f.read()

    def test_template_loads_packages_used_by_section_writing(self):
        source = self._template_source()
        loaded = set(re.findall(r"\\usepackage(?:\[[^\]]*\])?\{([^}]*)\}", source))
        packages = {name.strip() for group in loaded for name in group.split(",")}
        self.assertIn("graphicx", packages, "template.tex must load graphicx")
        self.assertIn("booktabs", packages, "template.tex must load booktabs")

    def test_template_compiles_generated_figure_and_table(self):
        if shutil.which("pdflatex") is None:
            self.skipTest("pdflatex is not installed")

        workdir = tempfile.mkdtemp(prefix="iclr_template_test_")
        self.addCleanup(shutil.rmtree, workdir, True)

        for name in os.listdir(TEMPLATE_DIR):
            shutil.copy(os.path.join(TEMPLATE_DIR, name), os.path.join(workdir, name))

        figures_dir = os.path.join(workdir, "figures")
        os.makedirs(figures_dir)
        with open(os.path.join(figures_dir, "plot.jpg"), "wb") as f:
            f.write(JPEG_BYTES)

        with open(os.path.join(workdir, "template.tex"), "w",
                  encoding="utf-8", newline="\n") as f:
            f.write(self._template_source().replace(PLACEHOLDER, BODY))

        result = subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", "template.tex"],
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=180,
        )

        errors = [
            line
            for line in result.stdout.splitlines()
            if line.startswith("! ")
        ]
        self.assertEqual(errors, [], f"LaTeX errors:\n" + "\n".join(errors[:5]))


if __name__ == "__main__":
    unittest.main()
