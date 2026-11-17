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

    # Optional: stop a Gemini API run once the estimated spend (USD) passes this amount
    PAPER_BUDGET_USD=0

    # if you want to run demo and send emails to yourself at the end, set these 2 fields as well
    SMTP_EMAIL=your_email
    SMTP_PASSWORD=your_password
    ```

## Running Without an API Key: Claude Code or Codex

Instead of the Gemini or OpenAI API, every LLM call can be sent to a locally installed and logged-in
[Claude Code](https://docs.anthropic.com/en/docs/claude-code) (`claude`) or Codex (`codex`) CLI, so a run uses an
existing Claude or ChatGPT subscription. Set in `.env` (see `.env.example` for all options):

```env
PAPER_LLM_BACKEND=claude   # or codex; leave unset to use the Gemini/OpenAI APIs
```

| Variable | Meaning |
|---|---|
| `PAPER_LLM_BACKEND` | `claude`, `codex`, or unset (Gemini/OpenAI APIs) |
| `PAPER_CLI_MODEL` | Model for writing and reviewing. Claude: `opus` (default) or `sonnet`. Codex: unset for its default |
| `PAPER_CLI_SEARCH_MODEL` | Model for literature-search calls (often 100+ per paper). Claude default: `sonnet` |
| `PAPER_CLI_FALLBACK` | On a usage limit, switch to the other CLI (`codex` or `claude`) |
| `PAPER_CLI_ON_LIMIT` | Without a fallback: `wait` (default, retry until the limit resets) or `stop` |
| `PAPER_CLI_WAIT_MINUTES`, `PAPER_CLI_MAX_WAIT_HOURS` | Retry interval while waiting (default 10) and maximum total wait (default 6) |
| `PAPER_CLI_CONCURRENCY`, `PAPER_CLI_TIMEOUT` | Parallel CLI sessions (default 3) and seconds per call (default 900) |

Notes:
- The literature agent's Google Search is replaced by the CLI's web search; paper metadata still comes from
  Semantic Scholar.
- PDF inputs are sent as extracted text, as the OpenAI path already does; images are passed as files.
- Model-name arguments such as `--writer_model_name` are ignored in this mode.
- If a run stops (usage limit, Ctrl+C), rerun the same command with `--resume` (see Key Arguments).
- A small example input is in `examples/minimal_materials/`.

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
*   `--resume`: Continue an interrupted run in the same `--output_dir`. Stages whose outputs already exist (outline, literature review, plots, draft) are skipped and the existing draft is kept; content refinement restarts from the draft. Without this flag, an existing output folder is overwritten.

### Interactive Demo

We provide an interactive Streamlit demo for the paper generation pipeline. For instructions on how to run and use it, please refer to the [README.md](frontend/README.md) in the `frontend` directory.

## Project Structure

*   `autoraters/`: Contains scripts for automated evaluation.
*   `methods/`: Core logic for agents and pipeline execution.
*   `templates/`: LaTeX templates for target conferences (`cvpr2025`, `iclr2025`, and `usenix2019` for USENIX venues such as OSDI, NSDI and ATC), you can add your own template by creating a new subfolder under this directory.
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
