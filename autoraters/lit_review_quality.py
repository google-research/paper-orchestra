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

import json
import os
import tqdm
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pydantic import BaseModel, Field

from pydantic import BaseModel, Field

from utils.llm_backend_utils import call_llm_with_pdf
from autoraters.prompts.lit_review_quality_prompts import (
    lit_review_quality_system_prompt,
)

# --- STRUCTURED OUTPUT SCHEMA ---


class SectionReview(BaseModel):
    score: int = Field(..., ge=0, le=100, description="Score 0-100 based on the rubric")
    justification: str = Field(
        ..., description="Critical analysis citing specific text."
    )


class PaperReview(BaseModel):
    paper_title: str = Field(..., description="Extracted title of the paper")
    clarity: SectionReview
    technical_depth: SectionReview
    connectivity: SectionReview
    presentation: SectionReview
    overall_quality_score: int = Field(..., description="Holistic score (0-100)")
    summary: str = Field(
        ..., description="A brief summary of the overall quality score justification."
    )


# --- END STRUCTURED OUTPUT SCHEMA ---

# Global lock for file writing
FILE_LOCK = threading.Lock()


def rate_single_paper(
    paper_pdf_path: str,
    model_name: str = "gemini-3.1-pro-preview",
    avg_citation_count: int = 58,
):
    try:
        with open(paper_pdf_path, "rb") as f:
            pdf_bytes = f.read()
    except FileNotFoundError:
        print(f"Error: File {paper_pdf_path} not found.")
        return ""

    max_retries = 5
    cur_try = 0
    succeed = False
    while (not succeed) and cur_try < max_retries:
        try:
            sys_instruct = lit_review_quality_system_prompt.format(
                avg_citation_count=avg_citation_count
            )
            response_dict = call_llm_with_pdf(
                pdf_path=paper_pdf_path,
                prompt="Rate this paper.",
                model_name=model_name,
                system_instruction=sys_instruct,
                temperature=0.0,
            )
            succeed = True
            return response_dict["parsed_response"]

        except Exception as e:
            print(
                f"Error processing {paper_pdf_path}: {e}. Retrying [{cur_try + 1}/{max_retries}]..."
            )
            cur_try += 1

    return ""


def _process_and_save_single_paper(
    paper_id: str,
    paper_path: str,
    output_json_path: str,
    current_ratings_dict: dict,
    avg_citation_count: int,
    model_name: str,
):
    """
    Helper function to run inside the thread.
    It rates the paper and immediately saves it to disk using a lock.
    """
    lit_rating = rate_single_paper(
        paper_path, avg_citation_count=avg_citation_count, model_name=model_name
    )

    if not lit_rating:
        return paper_id, False

    lit_rating["pdf_path"] = paper_path

    with FILE_LOCK:
        current_ratings_dict[paper_id] = lit_rating

        with open(output_json_path, "w") as f:
            json.dump(current_ratings_dict, f, indent=4)

    return paper_id, True


def perform_batch_rating(
    paper_path_dict: dict[str, str],
    output_json_path: str,
    max_workers: int = 10,
    avg_citation_count: int = 58,
    model_name: str = "gemini-3.1-pro-preview",
):
    if os.path.exists(output_json_path):
        with open(output_json_path, "r") as f:
            try:
                all_lit_ratings = json.load(f)
            except json.JSONDecodeError:
                all_lit_ratings = {}
                print(
                    f"Warning: {output_json_path} was corrupted or empty. Starting fresh."
                )
        print(
            f"Loaded {len(all_lit_ratings)-1} existing literature review ratings from '{output_json_path}'."
        )
    else:
        all_lit_ratings = {}

    papers_to_process = {}
    for paper_id, paper_path in paper_path_dict.items():
        if paper_id in all_lit_ratings:
            continue
        papers_to_process[paper_id] = paper_path

    total_to_process = len(papers_to_process)
    if total_to_process == 0:
        print("All papers have already been rated. Nothing to do.")
        return all_lit_ratings

    print(
        f"Starting parallel rating for {total_to_process} papers with {max_workers} threads..."
    )

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_paper = {
            executor.submit(
                _process_and_save_single_paper,
                pid,
                path,
                output_json_path,
                all_lit_ratings,
                avg_citation_count,
                model_name,
            ): pid
            for pid, path in papers_to_process.items()
        }

        for future in tqdm.tqdm(
            as_completed(future_to_paper), total=total_to_process, desc="Rating Papers"
        ):
            paper_id = future_to_paper[future]
            try:
                pid, success = future.result()
                if not success:
                    print(f"Failed to rate paper: {pid}")
            except Exception as exc:
                print(f"Paper {paper_id} generated an exception: {exc}")

    print(
        f"All {len(all_lit_ratings)} literature review ratings saved to {output_json_path}."
    )
    return all_lit_ratings


def perform_batch_rating_folder(
    root_folder: str,
    paper_rel_path="latex_writeup/final_paper.pdf",
    avg_citation_count: int = 58,
    model_name: str = "gemini-3.1-pro-preview",
):
    assert os.path.exists(root_folder), "Please provide a valid folder!"

    all_lit_ratings_save_path = os.path.join(
        root_folder,
        f"lit_review_quality_ratings_{model_name}_{paper_rel_path.split('/')[-1].replace('.pdf', '')}.json",
    )

    all_filename = os.listdir(root_folder)
    all_folders = []
    for filename in all_filename:
        if os.path.isdir(os.path.join(root_folder, filename)):
            all_folders.append(filename)
    all_folders.sort()

    paper_path_dict = {}
    for folder_name in tqdm.tqdm(all_folders, desc="Scanning folders"):
        paper_id = folder_name.strip()
        paper_path = os.path.join(root_folder, folder_name, paper_rel_path)
        if os.path.exists(paper_path):
            paper_path_dict[paper_id] = paper_path

    print(f"Extracted {len(paper_path_dict.keys())} papers from {root_folder}.")

    all_lit_ratings = perform_batch_rating(
        paper_path_dict=paper_path_dict,
        output_json_path=all_lit_ratings_save_path,
        max_workers=10,  # Adjustable based on API rate limits
        avg_citation_count=avg_citation_count,
        model_name=model_name,
    )

    print_literature_review_stats(all_lit_ratings_save_path)

    return all_lit_ratings


def print_literature_review_stats(file_path):
    """
    Parses a JSON file containing literature review evaluations and prints
    statistical averages for axis scores and the overall score.
    Saves overall metrics back to the JSON.
    """
    if not os.path.exists(file_path):
        print(f"Error: The file '{file_path}' was not found.")
        return

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError:
        print(
            f"Error: Failed to decode JSON from '{file_path}'. Please check the file format."
        )
        return
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return

    total_papers = 0
    total_overall_score_sum = 0
    axis_data = {}

    for paper_id, paper_content in data.items():
        if paper_id == "overall_metrics":
            continue

        total_papers += 1
        total_overall_score_sum += paper_content.get(
            "overall_score", paper_content.get("overall_quality_score", 0)
        )

        axis_scores_dict = paper_content.get("axis_scores", {})

        if not axis_scores_dict:
            for key in ["clarity", "technical_depth", "connectivity", "presentation"]:
                if (
                    key in paper_content
                    and isinstance(paper_content[key], dict)
                    and "score" in paper_content[key]
                ):
                    if key not in axis_data:
                        axis_data[key] = []
                    axis_data[key].append(paper_content[key]["score"])
        else:
            for axis_name, axis_details in axis_scores_dict.items():
                score = axis_details.get("score")
                if score is not None:
                    if axis_name not in axis_data:
                        axis_data[axis_name] = []
                    axis_data[axis_name].append(score)

    if total_papers == 0:
        print("No papers found in the JSON file.")
        return

    print("=" * 60)
    print(f"LITERATURE REVIEW EVALUATION STATS")
    print(f"Total Papers Processed: {total_papers}")
    print("=" * 60)
    print(f"{'Metric / Axis':<45} | {'Avg Score'}")
    print("-" * 60)

    overall_metrics = {}

    avg_overall = total_overall_score_sum / total_papers
    print(f"{'Overall Score':<45} | {avg_overall:.2f}")
    overall_metrics["overall_score"] = avg_overall
    print("-" * 60)

    for axis_name in sorted(axis_data.keys()):
        scores_list = axis_data[axis_name]
        avg_axis_score = sum(scores_list) / len(scores_list)
        formatted_name = axis_name.replace("_", " ").title()
        print(f"{formatted_name:<45} | {avg_axis_score:.2f}")
        overall_metrics[axis_name] = avg_axis_score

    print("=" * 60)

    data["overall_metrics"] = overall_metrics
    with open(file_path, "w") as f:
        json.dump(data, f, indent=4)


def perform_batch_rating_json(
    paper_info_json_path: str,
    avg_citation_count: int = 58,
    model_name: str = "gemini-3.1-pro-preview",
):
    with open(paper_info_json_path, "r") as f:
        paper_infos = json.load(f)
        print(f"Loaded {len(paper_infos)} papers from {paper_info_json_path}")

    paper_path_dict = {}
    for paper_info in paper_infos:
        if not os.path.exists(paper_info["pdf_path"]):
            print(f"{paper_info['pdf_path']} does not exist, skipping...")
            continue
        else:
            paper_path_dict[paper_info["paper_id"]] = paper_info["pdf_path"]

    print(
        f"Extracted {len(paper_path_dict.keys())} papers from {paper_info_json_path}."
    )

    output_json_path = paper_info_json_path.replace(
        ".json", "_lit_review_quality_ratings.json"
    )
    all_lit_ratings = perform_batch_rating(
        paper_path_dict=paper_path_dict,
        output_json_path=output_json_path,
        max_workers=10,
        avg_citation_count=avg_citation_count,
        model_name=model_name,
    )

    print_literature_review_stats(output_json_path)

    return all_lit_ratings
