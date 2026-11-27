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

### Criminology & Social-Science Mode

PaperOrchestra can also write **journal manuscripts for criminology, criminal justice, sociology, and related social sciences**, formatted in **APA 7th edition**.

```bash
python paper_writing_cli.py \
  --raw_materials_dir examples/criminology_example/raw_materials \
  --latex_template_dir templates/apa7_criminology \
  --output_dir ./paper_output_criminology_example \
  --use_plotting true
```

Choosing the `templates/apa7_criminology` template switches on the social-science mode automatically, because that folder contains a `domain.txt` file. You can also set it yourself with `--domain social_science` (or `--domain ai` for the original behavior).

What changes in this mode:

| Part of the pipeline | AI mode (original) | Social-science mode |
|---|---|---|
| Layout | CVPR / ICLR conference style | APA 7 manuscript (`apa7` class: double-spaced, masked for blind review, running head) |
| Citations | Numbered, BibTeX | APA author–date via `biblatex-apa` + `biber`: `\parencite{}` → (Smith, 2020), `\textcite{}` → Smith (2020) |
| Paper structure | Intro, Related Work, Method, Experiments | Introduction, Literature Review (ending with *The Current Study* and hypotheses), Data and Methods, Results, Discussion (with *Limitations*), Conclusion |
| Literature search | ArXiv and ML venues | Criminology and sociology journals, systematic reviews, official statistics |
| Writing rules | Benchmarks, ablations, state of the art | Theory-driven hypotheses; causal language only for causal designs; full statistical reporting (estimates, SEs/CIs, *N*, effect sizes); qualitative and mixed methods; ethics/IRB; person-first language; no ecological fallacy; limitations required |
| Simulated peer reviewer | ML conference reviewer | Criminology journal reviewer (theory, design, measurement, interpretation) |

**Input files.** The two files keep their names, but in this mode `idea_sparse.md` holds your research problem, theory, hypotheses, data and analysis plan, and `experimental_log.md` holds your *results log*: sample, descriptive statistics, model output, qualitative themes with quotes, and robustness checks. See `examples/criminology_example/` for a worked (fictional) example.

**Requirements.** Compiling the APA template needs a TeX installation with the `apa7`, `biblatex-apa` and `threeparttable` packages and the `biber` program (for example, on Debian/Ubuntu: `texlive-publishers texlive-bibtex-extra texlive-latex-extra biber`).

**Adapting to a specific journal.** Edit `templates/apa7_criminology/guidelines.md` to match your target journal's author instructions: word limit, abstract length, and whether tables go in the text or at the end. To put tables at the end, remove the `floatsintext` option from `template.tex`.

**Responsible use.** Check every sentence, number and citation in the output against your own data and the sources. Follow your university's and the journal's rules on disclosing AI assistance.

### Interactive Demo

We provide an interactive Streamlit demo for the paper generation pipeline. For instructions on how to run and use it, please refer to the [README.md](frontend/README.md) in the `frontend` directory.

## Project Structure

*   `autoraters/`: Contains scripts for automated evaluation.
*   `methods/`: Core logic for agents and pipeline execution.
*   `templates/`: LaTeX templates for target conferences and journals (`cvpr2025`, `iclr2025`, `apa7_criminology`). You can add your own template by creating a new subfolder under this directory; add a `domain.txt` containing `social_science` to use the social-science instructions with it.
*   `examples/`: Example input materials (`criminology_example` uses fictional data).
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
