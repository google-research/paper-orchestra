# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Selects the prompt set for a research domain.

- "ai" (default): the original prompts for ML/AI conference papers.
- "social_science": prompts for criminology, criminal justice, sociology and
  related fields (APA 7, journal-style manuscripts).
"""

SUPPORTED_DOMAINS = ("ai", "social_science")

_AI_DISCOVERY_SOURCES = (
    "Use Google Search to find REAL papers (ArXiv, CVPR, NeurIPS, ICML, ICLR, etc.)."
)
_AI_DISCOVERY_QUALITY_RULE = (
    "Only return papers published in top-tier conferences or journals, or "
    "highly-cited works, or the exact state-of-the-art relevant to the task."
)


def check_domain(domain: str) -> str:
    if domain not in SUPPORTED_DOMAINS:
        raise ValueError(
            f"Unknown domain '{domain}'. Choose one of: {', '.join(SUPPORTED_DOMAINS)}"
        )
    return domain


def get_prompts(domain: str = "ai") -> dict:
    """Returns a dict of all domain-dependent prompts.

    Keys: outline, lit_review_writer, lit_discovery_sources,
    lit_discovery_quality_rule, section_writing, content_refinement,
    reviewer_system (None = AgentReview default), meta_reviewer_system
    (None = AgentReview default), lit_writer_user_prompt.
    """
    check_domain(domain)

    if domain == "social_science":
        from methods.prompts import social_science as ss

        return {
            "outline": ss.outline_agent_system_prompt,
            "lit_review_writer": ss.literature_review_agent_writter_prompt,
            "lit_writer_user_prompt": "Generate the LaTeX for the Introduction and Literature Review sections.",
            "lit_discovery_sources": ss.literature_discovery_sources,
            "lit_discovery_quality_rule": ss.literature_discovery_quality_rule,
            "section_writing": ss.section_writing_agent_prompt,
            "content_refinement": ss.content_refinement_agent_system_prompt,
            "reviewer_system": ss.reviewer_system_prompt,
            "meta_reviewer_system": ss.meta_reviewer_system_prompt,
        }

    from methods.prompts.outline_agent import outline_agent_system_prompt
    from methods.prompts.literature_review_agent import (
        literature_review_agent_writter_prompt,
    )
    from methods.prompts.section_writing_agent import section_writing_agent_prompt
    from methods.prompts.content_refinement_agent import (
        content_refinement_agent_system_prompt,
    )

    return {
        "outline": outline_agent_system_prompt,
        "lit_review_writer": literature_review_agent_writter_prompt,
        "lit_writer_user_prompt": "Generate the LaTeX for Introduction and Related Work sections.",
        "lit_discovery_sources": _AI_DISCOVERY_SOURCES,
        "lit_discovery_quality_rule": _AI_DISCOVERY_QUALITY_RULE,
        "section_writing": section_writing_agent_prompt,
        "content_refinement": content_refinement_agent_system_prompt,
        "reviewer_system": None,
        "meta_reviewer_system": None,
    }
