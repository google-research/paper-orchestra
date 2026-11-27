# Criminology example (fictional data)

This folder shows the **format** of the two input files PaperOrchestra needs for a
social-science paper. Every number in it is **made up** for testing the pipeline.
Do not cite or submit a paper generated from these files.

- `raw_materials/idea_sparse.md`: the research problem, theory, hypotheses, data and analytic plan.
- `raw_materials/experimental_log.md`: the results log (sample, descriptive statistics, model output, robustness checks).
- `raw_materials/figures/`: optional, for figures you made yourself (leave empty when using `--use_plotting true`).

Run it from the repository root:

```bash
python paper_writing_cli.py \
  --raw_materials_dir examples/criminology_example/raw_materials \
  --latex_template_dir templates/apa7_criminology \
  --output_dir ./paper_output_criminology_example \
  --research_cutoff 2025-06 \
  --use_plotting true
```
