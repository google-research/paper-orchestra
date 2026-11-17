# Claude frontend

From the repository root:

```bash
pip install -r requirements-frontend.txt
streamlit run frontend/app.py
```

Configure the private `.env` as described in the root README. The frontend uses the same Claude backend, preserves author-provided figures, and disables automatic image generation. It passes `--stream_logs` to the CLI for live progress; Markdown reports and usage records remain in the run directory. The inherited email notification feature is optional and requires your SMTP settings. Browser interactions have not been validated by the offline unit tests.
