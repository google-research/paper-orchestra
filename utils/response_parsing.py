"""Provider-independent parsers for structured writing responses."""

import json
import re


def identity_parse(response: str):
    return response


def parse_json_results(response: str):
    if not isinstance(response, str) or not response.strip():
        return None
    fenced = re.findall(r"```json\s*(.*?)\s*```", response, re.DOTALL)
    for candidate in [*fenced, response.strip()]:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
    decoder = json.JSONDecoder()
    for match in re.finditer(r"[\[{]", response):
        try:
            value, _ = decoder.raw_decode(response[match.start():])
            return value
        except json.JSONDecodeError:
            pass
    return None


def parse_latex_results(response: str):
    match = re.search(r"```(?:latex|tex)\s*(.*?)\s*```", response.strip(), re.DOTALL)
    return match.group(1).strip() if match else response.strip()


def parse_json_latex_response(response: str):
    """Keep the upstream refinement agent's JSON-string return contract."""
    worklog = re.search(r"```json\s*(.*?)\s*```", response, re.DOTALL)
    latex = re.search(r"```(?:latex|tex)\s*(.*?)\s*```", response, re.DOTALL)
    if not worklog or not latex or not latex.group(1).strip():
        raise ValueError("Refinement requires both a JSON worklog and a LaTeX block")
    return json.dumps({"json": json.loads(worklog.group(1)), "latex": latex.group(1)})
