# <div align="center">🎻 PaperOrchestra: A Multi-Agent Framework for Automated AI Research Paper Writing</div>
<div align="center">Yiwen Song<sup>1</sup>, Yale Song<sup>1</sup>, Tomas Pfister<sup>1</sup>, and Jinsung Yoon<sup>1</sup></div>
<div align="center"><sup>1</sup>Google Cloud AI Research</div>
<br><br>

PaperOrchestra is a multi-agent framework for automated AI research paper writing. It flexibly transforms unconstrained pre-writing materials (ideas and experimental logs) into submission-ready LaTeX manuscripts, including comprehensive literature synthesis and generated visuals, such as plots and conceptual diagrams.

Acting like an orchestrated team of specialized agents, it handles outline generation, literature review, section writing, content refinement, and plotting to close the gap between raw research materials and submission ready papers.

<div align="center">
  <img src="assets/overview.png" alt="PaperOrchestra Overview" width="90%"/>
</div>

## Key Features

- **Multi-Agent Pipeline**: Orchestrates specialized agents (Outline, Literature Review, Section Writing, Content Refinement, Plotting) for end-to-end paper generation.
- **Comprehensive Literature Synthesis**: Automatically searches, prioritizes, and integrates relevant literature into the manuscript.
- **Visuals Generation**: Generates plots and supports the inclusion of conceptual diagrams.
- **LaTeX Automation**: Produces submission-ready LaTeX manuscripts adhering to target conference templates.

## About this fork: run on Claude Code or Codex, no API key needed

This fork of [google-research/paper-orchestra](https://github.com/google-research/paper-orchestra) adds a
switch that sends every LLM call to the **Claude Code** or **Codex** command-line tool you are already logged in
to, so a run uses your Claude or ChatGPT subscription instead of a paid Gemini API key. Nothing else in the
pipeline changes.

### Quick start

```bash
git clone https://github.com/Tusherbhomik/paper-orchestra.git
cd paper-orchestra
conda create -n paper_orchestra python=3.11 -y
conda activate paper_orchestra
pip install -r requirements.txt
cp .env.example .env          # PAPER_LLM_BACKEND=claude is already set
```

You also need:
- **Claude Code** (`claude` on your PATH, logged in), or **Codex** (`codex` on your PATH, logged in) with
  `PAPER_LLM_BACKEND=codex` in `.env`;
- **LaTeX** with `pdflatex` and `bibtex` (for example TeX Live), used to compile the paper.

Put your materials in a folder with two files, `idea_sparse.md` (problem, idea, method, contributions) and
`experimental_log.md` (setup and every number you want in the paper, as tables). Figures are optional: add a
`figures/` subfolder with the image files and an `info.json` listing them, for example
`[{"name": "result.png", "caption": "What the figure shows."}]`. Then run:

```bash
python paper_writing_cli.py \
  --raw_materials_dir path/to/your_materials \
  --latex_template_dir templates/iclr2025 \
  --output_dir ./paper_output_mypaper
```

Templates: `templates/iclr2025`, `templates/cvpr2025`, and `templates/usenix2019` (this fork; two-column USENIX
format for OSDI, NSDI and ATC). To add rules for one paper (scope, claims to avoid), put them in your
`idea_sparse.md`, or copy a template folder under `my_inputs/` and pass that path.

The paper is written to `paper_output_mypaper/`. Anything under `my_inputs/` and `paper_output*/` is ignored by
git, so your unpublished work is not committed by accident.

### Settings (`.env`)

| Variable | Meaning |
|---|---|
| `PAPER_LLM_BACKEND` | `claude`, `codex`, or empty for the Gemini API |
| `PAPER_CLI_MODEL` | Model for the CLI. Claude: `opus` (default) or `sonnet`. Codex: empty for its default |
| `PAPER_CLI_CONCURRENCY` | CLI sessions at once (default 3) |
| `PAPER_CLI_TIMEOUT` | Seconds allowed per call (default 900) |
| `PAPER_BUDGET_USD` | Gemini API mode only: stop once the estimated spend passes this amount (0 = no limit) |

### Good to know

- **Usage limits.** A full paper is roughly 50–80 calls with large prompts. If your subscription's usage limit
  is reached, the run stops with the reason; a rerun starts from the beginning. `sonnet` uses less than `opus`.
- **Time.** Each call starts a CLI session; a full paper takes roughly 30–90 minutes.
- **Literature search** uses Claude's or Codex's web search in place of Google Search. Paper metadata still comes
  from Semantic Scholar (no key needed).
- **PDFs.** Where the pipeline sends Gemini a compiled PDF, the CLI receives its extracted text (as the repo's
  OpenAI path already does). Page images are still passed as images.
- **Model flags** such as `--writer_model_name` are ignored in CLI mode.
- **Check the output.** Citations come from web search and Semantic Scholar, and the text is generated; verify
  every claim, number and reference. Check your venue's policy on AI-generated text before submitting.
- **Data leaves your machine.** Your materials are sent to Anthropic (Claude) or OpenAI (Codex).

### What was changed from upstream

- `utils/cli_backend.py` (new): runs each call through `claude -p` or `codex exec`, passes images as files,
  turns on web search for the literature agent, limits concurrency, and stops on usage-limit or login errors.
- `utils/gemini_utils.py`: `call_gemini_with_contents`, which every Gemini call goes through, hands calls to the
  CLI backend when `PAPER_LLM_BACKEND` is set. Also: the Gemini client uses API version `v1beta` (preview models
  are not served on `v1`), and an optional spend guard (`PAPER_BUDGET_USD`) logs and caps estimated Gemini cost.
- `templates/usenix2019/` (new): USENIX two-column template (`usenix2019_v3.sty`, the official sample files,
  `template.tex` and `guidelines.md` for the writer).
- `.env.example` (new); `my_inputs/`, `paper_output*/` and `__pycache__/` are ignored by git.

The original README follows.

## Installation

1.  **Environment Setup**: The project relies on a Conda environment named `paper_orchestra`. You can set up a similar environment with Python 3.11 and install the required dependencies.
    ```bash
    conda create -n paper_orchestra python=3.11
    conda activate paper_orchestra
    pip install -r requirements.txt
    ```

2.  **Environment Variables**: Create a `.env` file in the root of the project and add your API keys:
    ```env
    # Add keys if you have them, otherwise leave them empty
    # You need to specify related keys if you want to use the model
    # For example, if you want to use Gemini models, you need to specify either VERTEX_AI_PROJECT and VERTEX_AI_LOCATION, or GEMINI_API_KEY
    # If you want to use OpenAI models, you need to specify OPENAI_API_KEY
    
    SEMANTIC_SCHOLAR_API_KEY=your_semantic_scholar_api_key
    OPENAI_API_KEY=your_openai_api_key
    VERTEX_AI_PROJECT=your_vertex_ai_project
    VERTEX_AI_LOCATION=your_vertex_ai_location
    GEMINI_API_KEY=your_gemini_api_key

    # if you want to run demo and send emails to yourself at the end, set these 2 fields as well
    SMTP_EMAIL=your_email
    SMTP_PASSWORD=your_password
    ```

## Dataset

The dataset used for paper generation is **not included** in this code repository. It will be released separately at a later date.
Once available, you should download the dataset and place it under the `datasets/` directory.

## Usage

You can run the paper generation pipeline using the provided bash script or directly via the Python CLI.

### Using the Bash Script
```bash
./paper_writing_cli.sh
```

### Using the Python CLI directly
```bash
python paper_writing_cli.py \
  --raw_materials_dir /path_to_your_raw_materials/ \
  --latex_template_dir /path_to_your_latex_template/ \
  --output_dir /path_to_your_output_folder/ \
  --use_plotting true
```

### Key Arguments
*   `--raw_materials_dir`: (Required) Directory containing the raw materials (e.g., idea and experimental log).
*   `--latex_template_dir`: (Required) Directory containing the LaTeX template (e.g., `templates/cvpr2025`).
*   `--output_dir`: Directory to output the generated paper. If not specified, an automatic folder with a timestamp is created.
*   `--use_plotting`: Enable the plotting agent workflow to generate figures from code (Default: `False`).
*   `--writer_model_name`: LLM for writer and literature agents.
*   `--reflection_model_name`: LLM for reflection agents.

### Interactive Demo

We provide an interactive Streamlit demo for the paper generation pipeline. For instructions on how to run and use it, please refer to the [README.md](frontend/README.md) in the `frontend` directory.

## Project Structure

*   `autoraters/`: Contains scripts for automated evaluation.
*   `methods/`: Core logic for agents and pipeline execution.
*   `templates/`: LaTeX templates for target conferences, you can add your own template by creating a new subfolder under this directory.
*   `utils/`: Utility functions for API calls, PDF handling, etc.

## Citation

If you find this repo or our paper helpful, please cite it as follows:

```bibtex
@article{song2026paperorchestra,
  title={PaperOrchestra: A Multi-Agent Framework for Automated AI Research Paper Writing},
  author={Song, Yiwen and Song, Yale and Pfister, Tomas and Yoon, Jinsung},
  journal={arXiv preprint arXiv:2604.05018},
  year={2026}
}
```

# Disclaimer

This is not an officially supported Google product.
