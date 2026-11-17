"""Compatibility entry point: this Claude fork uses author-provided figures."""


def write_single_paper(*args, **kwargs):
    raise NotImplementedError(
        "Automatic plotting is disabled in the Claude fork. Supply verified figures "
        "and run paper_writing_cli.py with --use_plotting false."
    )


def run_batch_writeup(*args, **kwargs):
    return write_single_paper(*args, **kwargs)
