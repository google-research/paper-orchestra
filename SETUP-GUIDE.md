PaperOrchestra is installed and ready except for your API keys; I have not run the pipeline, since it can't start without one.

What I did:

- **Clone:** the repo is in `paper-orchestra/` inside your `computing-systems` folder.
- **Environment:** conda env `paper_orchestra` (Python 3.11) with everything from `requirements.txt` installed; the main imports load.
- **LaTeX:** `pdflatex` and `bibtex` are already on your system, which is what it uses to compile.
- **Keys file:** an empty `.env` template (already gitignored).

What you need to do:

1. **Add a key to `.env`.** The default models are all Gemini (`gemini-3.1-pro-preview`, plus `gemini-3-pro-image-preview` for figures), so `GEMINI_API_KEY` is the one that matters. `SEMANTIC_SCHOLAR_API_KEY` is optional. `OPENAI_API_KEY` is only needed if you pass an OpenAI model name.

2. **Prepare your inputs.** The official dataset is not released yet, so you supply your own folder with two files:
   - `idea_sparse.md`: your idea and method description.
   - `experimental_log.md`: your setup, results and numbers.

3. **Run it:**

   ```bash
   conda activate paper_orchestra
   cd "/home/tusher/Downloads/computing-systems/paper-orchestra"
   python paper_writing_cli.py \
     --raw_materials_dir /path/to/your_raw_materials \
     --latex_template_dir templates/iclr2025 \
     --output_dir ./paper_output_test \
     --use_plotting true
   ```

   Or use the web UI with `streamlit run frontend/app.py`, which opens at `http://localhost:8501`.

Things to know before you run it:

- **Templates:** only CVPR 2025 and ICLR 2025 ship with the repo. For a USENIX-style paper you would add a folder under `templates/` with `template.tex`, `guidelines.md`, the style files and a `references.bib`, modelled on the existing two.
- **Don't use the bash script as is:** `paper_writing_cli.sh` points at a dataset paper ID that doesn't exist locally.
- **Key printed to logs:** on startup it prints your Semantic Scholar key in plain text, so don't share those logs.
- **Cost:** a full run makes many calls to the pro model across five agents, and plotting adds image-model calls. Leave `--use_plotting` off for a cheaper first test.
