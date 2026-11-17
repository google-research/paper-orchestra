"""Shared Claude-only interface for writing, review, images, and PDF documents."""

from pathlib import Path
from utils.anthropic_utils import (
    DEFAULT_MODEL, bytes_part, text_part, image_part, validate_model,
    call_claude_with_contents,
)
from utils.response_parsing import (
    identity_parse, parse_json_results, parse_latex_results, parse_json_latex_response,
)


def get_llm_parser(model_name=DEFAULT_MODEL, return_json=True):
    validate_model(model_name)
    return parse_json_results if return_json else identity_parse


def call_llm_with_contents(
    contents, model_name=DEFAULT_MODEL, generation_configs=None,
    check_parsed_response_not_none=True, return_json=True, result_parsing_func=None,
):
    return call_claude_with_contents(
        contents=contents, model_name=model_name, generation_configs=generation_configs,
        result_parsing_func=result_parsing_func or get_llm_parser(model_name, return_json),
        check_parsed_response_not_none=check_parsed_response_not_none,
    )


def call_llm_with_text_prompt(prompt, model_name=DEFAULT_MODEL, **kwargs):
    return call_llm_with_contents([prompt], model_name=model_name, **kwargs)


def call_llm_with_images(prompt, images, model_name=DEFAULT_MODEL, **kwargs):
    return call_llm_with_contents(
        [text_part(prompt), *(image_part(path) for path in images)],
        model_name=model_name, **kwargs,
    )


def call_llm_with_pdf(
    pdf_path, prompt, model_name=DEFAULT_MODEL, system_instruction=None,
    temperature=0.7, **kwargs,
):
    config = dict(kwargs.pop("generation_configs", {}) or {})
    if system_instruction:
        config["system_instruction"] = system_instruction
    return call_llm_with_contents(
        [bytes_part(Path(pdf_path).read_bytes(), "application/pdf"), text_part(prompt)],
        model_name=model_name, generation_configs=config, **kwargs,
    )
