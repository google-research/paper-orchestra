# <div align="center">🎻 PaperOrchestra: A Multi-Agent Framework for Automated AI Research Paper Writing</div>
<div align="center">Yiwen Song<sup>1</sup>, Yale Song<sup>1</sup>, Tomas Pfister<sup>1</sup>, and Jinsung Yoon<sup>1</sup></div>
<div align="center"><sup>1</sup>Google Cloud AI Research</div>
<br><br>

> **This fork runs PaperOrchestra on Claude Code or Codex, with no API key.**
> Jump to [Getting started](#getting-started-with-claude-code-or-codex). The original Gemini-only instructions are
> further down.

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

### Getting started with Claude Code or Codex

**Step 1. Check you have the tools.** Each command should print a version:

```bash
claude --version      # Claude Code, logged in to your Claude account   (or)
codex --version       # Codex CLI, logged in to your ChatGPT account
pdflatex --version    # LaTeX, e.g. TeX Live (sudo apt install texlive-full on Ubuntu)
conda --version       # Miniconda or Anaconda
```

You need **one** of `claude` or `codex`, plus `pdflatex` (which comes with `bibtex`) and `conda`.

**Step 2. Install.**

```bash
git clone https://github.com/Tusherbhomik/paper-orchestra.git
cd paper-orchestra
conda create -n paper_orchestra python=3.11 -y
conda activate paper_orchestra
pip install -r requirements.txt
cp .env.example .env
```

`.env` is set to Claude. For Codex, open `.env` and change the line to `PAPER_LLM_BACKEND=codex`.

**Step 3. Try the example.** A small made-up input is included in `examples/minimal_materials/`:

```bash
python paper_writing_cli.py \
  --raw_materials_dir examples/minimal_materials \
  --latex_template_dir templates/usenix2019 \
  --output_dir ./paper_output_example
```

You will see lines like `🤖 claude/opus call 1: ...`. When it finishes, open
`paper_output_example/final_paper.pdf`. A full run is long (see the stage table below); press Ctrl+C at any time
and continue later with `--resume` (Step 5).

**Step 4. Write your own paper.** Make a folder, for example `my_inputs/mypaper/` (git ignores `my_inputs/`),
with two files modelled on the example:

| File | What to put in it |
|---|---|
| `idea_sparse.md` | Problem, hypothesis, approach, contributions, and what must **not** be claimed |
| `experimental_log.md` | Setup, and **every number** you want in the paper, as tables. The writer only sees what is here |
| `figures/` (optional) | Your figure images (`.png`, `.jpg`) and an `info.json`: `[{"name": "result.png", "caption": "What it shows."}]` |

Then run, choosing a template (`templates/usenix2019` for OSDI/NSDI/ATC, `templates/iclr2025`,
`templates/cvpr2025`):

```bash
python paper_writing_cli.py \
  --raw_materials_dir my_inputs/mypaper \
  --latex_template_dir templates/usenix2019 \
  --output_dir ./paper_output_mypaper
```

Without a `figures/` folder you get a warning; add `--use_plotting true` to have figures generated, or ignore it.
Output folders (`paper_output*/`) are ignored by git, so your unpublished work is not committed by accident.

**Step 5. If it stops (usage limit, Ctrl+C, crash), continue with `--resume`.** Run the same command with the same
`--output_dir` and add `--resume`; finished stages are skipped. Details in
[If you hit a usage limit](#if-you-hit-a-usage-limit).

### Settings (`.env`)

| Variable | Meaning |
|---|---|
| `PAPER_LLM_BACKEND` | `claude`, `codex`, or empty for the Gemini API |
| `PAPER_CLI_MODEL` | Model for writing and reviewing. Claude: `opus` (default) or `sonnet`. Codex: empty for its default |
| `PAPER_CLI_SEARCH_MODEL` | Model for the literature-search calls (100+ per paper). Claude default: `sonnet` |
| `PAPER_CLI_FALLBACK` | When the main CLI hits its usage limit, switch to this one (`codex` or `claude`) |
| `PAPER_CLI_FALLBACK_MODEL` | Model for the fallback CLI (optional) |
| `PAPER_CLI_ON_LIMIT` | Without a fallback: `wait` (default) for the limit to reset, or `stop` |
| `PAPER_CLI_WAIT_MINUTES` | While waiting, retry every this many minutes (default 10) |
| `PAPER_CLI_MAX_WAIT_HOURS` | Give up waiting after this long (default 6) |
| `PAPER_CLI_CONCURRENCY` | CLI sessions at once (default 3) |
| `PAPER_CLI_TIMEOUT` | Seconds allowed per call (default 900) |
| `PAPER_BUDGET_USD` | Gemini API mode only: stop once the estimated spend passes this amount (0 = no limit) |

### What a run does, stage by stage

| Stage | Calls (approx.) | Output in `--output_dir` | Kept by `--resume`? |
|---|---|---|---|
| 1. Outline | 1 | `outline.json` | yes |
| 2. Literature review: web searches, then Introduction and Related Work | 20–120 small + 1 large | `literature_agent_output/` | yes |
| 2b. Plots (only with `--use_plotting true`) | several per figure | `plotting_results.json`, `figures/` | yes |
| 3. Section writing: the full draft | 1 large | `latex_writeup/raw_draft_paper.tex` | yes |
| 4. Refinement: 3 rounds of reviews and rewrites, then a formatting pass | about 15–20 large | `content_refinement_workdir/`, `final_paper.pdf` | restarts from the draft |

The search stage makes the most calls but they are small; stages 3 and 4 send the whole paper each time and use
most of your quota.

### If you hit a usage limit

Claude and ChatGPT plans have rolling usage limits (for example Claude's 5-hour limit). This fork handles them:

1. **Automatically, by default.** When the CLI reports a usage limit, the run **waits** and retries every
   `PAPER_CLI_WAIT_MINUTES` until the limit resets (up to `PAPER_CLI_MAX_WAIT_HOURS`). You can leave it running.
2. **Or switch tools.** With `PAPER_CLI_FALLBACK=codex` (or `claude`), the run moves to the other CLI as soon as
   the first one is limited, and stays there.
3. **Or stop and continue later.** Press Ctrl+C at any time, or set `PAPER_CLI_ON_LIMIT=stop`. Then run **the
   same command again with `--resume`**:

   ```bash
   python paper_writing_cli.py \
     --raw_materials_dir path/to/your_materials \
     --latex_template_dir templates/iclr2025 \
     --output_dir ./paper_output_mypaper \
     --resume
   ```

   Stages whose output already exists are skipped (you will see `⏭️ Resume: skipping ...`). Use the **same**
   `--output_dir`, materials and template.

**Never rerun without `--resume` on an output folder you want to keep:** a normal run deletes the previous draft
in that folder and starts over. To be safe, copy the folder first (`cp -a paper_output_mypaper backup_x`).

To redo one stage, delete its output and resume: for example delete `latex_writeup/raw_draft_paper.tex` to
rewrite the draft from the existing outline and literature review.

To use less quota: `PAPER_CLI_MODEL=sonnet`, and keep `PAPER_CLI_SEARCH_MODEL` at `sonnet` (or `haiku`).

### Good to know

- **Time.** Each call starts a CLI session; a full paper takes roughly 1–2 hours of calls.
- **Literature search** uses Claude's or Codex's web search in place of Google Search. Paper metadata then comes
  from Semantic Scholar; without a key it is rate-limited and may drop candidates, so a free
  `SEMANTIC_SCHOLAR_API_KEY` can give a larger bibliography.
- **PDFs.** Where the pipeline sends Gemini a compiled PDF, the CLI receives its extracted text (as the repo's
  OpenAI path already does). Page images are still passed as images.
- **Model flags** such as `--writer_model_name` are ignored in CLI mode; the review log still prints the Gemini
  model name, which can be ignored.
- **Check the output.** Citations come from web search and Semantic Scholar, and the text is generated; verify
  every claim, number and reference. Check your venue's policy on AI-generated text before submitting.
- **Data leaves your machine.** Your materials are sent to Anthropic (Claude) or OpenAI (Codex).

### Troubleshooting

| You see | What to do |
|---|---|
| `⏳ ... usage limit ... Waiting` | Normal: it waits for your limit to reset. Or set `PAPER_CLI_FALLBACK=codex`, or Ctrl+C and `--resume` later |
| `out of usage credits` / `model_requires_usage_credits` | Your plan has no access to that Claude model; set `PAPER_CLI_MODEL=sonnet` (or `opus`) |
| `🛑 CLI backend stopped` with a login message | Run `claude` (or `codex`) once in a terminal and log in, then `--resume` |
| `claude: command not found` / `codex: command not found` | Install the CLI and make sure it is on your PATH, or switch `PAPER_LLM_BACKEND` |
| `WARNING: No figures ... detected` | Add a `figures/` folder with `info.json`, or use `--use_plotting true`, or ignore it |
| LaTeX errors, or no PDF | Check `pdflatex --version`; install a full TeX distribution (e.g. `texlive-full`) |
| Very few references in the paper | Add a free `SEMANTIC_SCHOLAR_API_KEY` to `.env`, delete `literature_agent_output/` and `latex_writeup/raw_draft_paper.tex` in the output folder, and `--resume` |
| `404 NOT_FOUND ... gemini` | You are in Gemini API mode; set `PAPER_LLM_BACKEND=claude` or `codex` in `.env` |

### What was changed from upstream

- `utils/cli_backend.py` (new): runs each call through `claude -p` or `codex exec`, passes images as files,
  turns on web search for the literature agent with its own (cheaper) model, limits concurrency, and on a usage
  limit waits, switches CLI or stops; login errors stop the run.
- `--resume` flag (`paper_writing_cli.py`, `methods/paper_writer*.py`, new `utils/resume_utils.py`): skips stages
  whose output already exists and no longer deletes the previous draft when resuming.
- `utils/gemini_utils.py`: `call_gemini_with_contents`, which every Gemini call goes through, hands calls to the
  CLI backend when `PAPER_LLM_BACKEND` is set. Also: the Gemini client uses API version `v1beta` (preview models
  are not served on `v1`), and an optional spend guard (`PAPER_BUDGET_USD`) logs and caps estimated Gemini cost.
- `templates/usenix2019/` (new): USENIX two-column template (`usenix2019_v3.sty`, the official sample files,
  `template.tex` and `guidelines.md` for the writer).
- `examples/minimal_materials/` (new): a small example input.
- `.env.example` (new); `my_inputs/`, `paper_output*/` and `__pycache__/` are ignored by git.

The original README follows. Its Installation section is for the **Gemini API** only; for Claude Code or Codex
follow [Getting started](#getting-started-with-claude-code-or-codex) above.

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
