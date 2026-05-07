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
import threading
import base64
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from google.genai import types
import pymupdf  # type: ignore

from utils.pdf_utils import load_paper
from utils.llm_backend_utils import get_llm_parser
from utils.gemini_utils import call_gemini_with_contents
from utils.openai_utils import call_openai_models_with_content
from autoraters.prompts.sxs_quality_prompts import sxs_paper_quality_system_prompt

# Global lock for file writing
FILE_LOCK = threading.Lock()


def get_pdf_page_images_base64(pdf_path, max_pages=None):
    doc = pymupdf.open(pdf_path)
    b64_images = []
    for i, page in enumerate(doc):
        if max_pages and i >= max_pages:
            break
        # Extract image bytes at screen resolution
        pix = page.get_pixmap()
        img_bytes = pix.tobytes("jpeg")
        b64_str = base64.b64encode(img_bytes).decode("utf-8")
        b64_images.append(b64_str)
    return b64_images


def rate_sxs_paper_quality(
    paper1_path: str, paper2_path: str, model_name: str = "gemini-3.1-pro-preview"
):
    max_retries = 5
    cur_try = 0
    succeed = False

    prompt_text = "Task: Compare the overall scientific contribution, technical depth, formatting, presentation, and writing quality of these two papers side by side."

    is_openai = (
        "gpt" in model_name.lower()
        or "o1" in model_name.lower()
        or "o3" in model_name.lower()
    )

    while (not succeed) and cur_try < max_retries:
        try:
            if is_openai:
                # Setup OpenAI content payload
                paper1_text = load_paper(paper1_path, min_size=100)
                paper2_text = load_paper(paper2_path, min_size=100)

                content = []
                content.append(
                    {"type": "text", "text": "Paper 1 Text:\n" + paper1_text}
                )
                content.append({"type": "text", "text": "Paper 1 Visual Pages:"})

                for b64_img in get_pdf_page_images_base64(paper1_path, max_pages=15):
                    content.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"},
                        }
                    )

                content.append(
                    {"type": "text", "text": "Paper 2 Text:\n" + paper2_text}
                )
                content.append({"type": "text", "text": "Paper 2 Visual Pages:"})

                for b64_img in get_pdf_page_images_base64(paper2_path, max_pages=15):
                    content.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"},
                        }
                    )

                content.append({"type": "text", "text": prompt_text})

                response_dict = call_openai_models_with_content(
                    content=content,
                    model_name=model_name,
                    result_parsing_func=get_llm_parser(model_name, return_json=True),
                    check_parsed_response_not_none=True,
                    system_prompt=sxs_paper_quality_system_prompt,
                )
            else:
                # Setup Gemini
                with open(paper1_path, "rb") as f1, open(paper2_path, "rb") as f2:
                    pdf1_bytes = f1.read()
                    pdf2_bytes = f2.read()

                contents = [
                    types.Part.from_text(text="Paper 1:"),
                    types.Part.from_bytes(data=pdf1_bytes, mime_type="application/pdf"),
                    types.Part.from_text(text="\n\nPaper 2:"),
                    types.Part.from_bytes(data=pdf2_bytes, mime_type="application/pdf"),
                    types.Part.from_text(text="\n\n" + prompt_text),
                ]

                response_dict = call_gemini_with_contents(
                    contents=contents,
                    model_name=model_name,
                    result_parsing_func=get_llm_parser(model_name, return_json=True),
                    generation_configs={
                        "temperature": 0.0,
                        "system_instruction": sxs_paper_quality_system_prompt,
                    },
                    check_parsed_response_not_none=True,
                )

            succeed = True
            return (
                response_dict.get("parsed_response", response_dict)
                if isinstance(response_dict, dict)
                else response_dict
            )

        except Exception as e:
            print(
                f"Error processing SxS (model={model_name}): {e}. Retrying [{cur_try + 1}/{max_retries}]...",
                flush=True,
            )
            cur_try += 1
            if cur_try < max_retries:
                time.sleep(5)

    return {}


def _process_and_save_single_sxs(
    paper_id: str,
    paper1_path: str,
    paper2_path: str,
    output_json_path: str,
    current_results_dict: dict,
    model_name: str,
    exp1_name: str,
    exp2_name: str,
):
    """
    Helper function to run inside the thread. Rates SxS paper quality twice (both orders) and aggregates.
    """
    rating1 = rate_sxs_paper_quality(paper1_path, paper2_path, model_name=model_name)
    rating2 = rate_sxs_paper_quality(paper2_path, paper1_path, model_name=model_name)

    if not rating1 or not rating2:
        print(
            f"❌ [{paper_id}] Failed to get ratings for one or both rounds.", flush=True
        )
        return paper_id, False

    winner1 = rating1.get("winner", "").lower() if isinstance(rating1, dict) else ""
    winner2 = rating2.get("winner", "").lower() if isinstance(rating2, dict) else ""

    r1_result = "tie"
    if "paper_1" in winner1 or "paper 1" in winner1:
        r1_result = "p1"
    elif "paper_2" in winner1 or "paper 2" in winner1:
        r1_result = "p2"

    r2_result = "tie"
    if "paper_1" in winner2 or "paper 1" in winner2:
        r2_result = "p2"  # Swap!
    elif "paper_2" in winner2 or "paper 2" in winner2:
        r2_result = "p1"

    s1 = 1 if r1_result == "p1" else (-1 if r1_result == "p2" else 0)
    s2 = 1 if r2_result == "p1" else (-1 if r2_result == "p2" else 0)
    total_score = s1 + s2

    category_5pt = "tie"
    if total_score == 2:
        category_5pt = "win"
    elif total_score == 1:
        category_5pt = "leaning_win"
    elif total_score == -1:
        category_5pt = "leaning_loss"
    elif total_score == -2:
        category_5pt = "loss"
    else:
        category_5pt = "tie"

    category_3pt = "tie"
    if total_score > 0:
        category_3pt = "win"
    elif total_score < 0:
        category_3pt = "loss"
    else:
        category_3pt = "tie"

    result_entry = {
        "run1": rating1,
        "run2": rating2,
        "p1_result_run1": r1_result,
        "p1_result_run2": r2_result,
        "total_score": total_score,
        "category_5pt": category_5pt,
        "category_3pt": category_3pt,
        "paper_1_path": paper1_path,
        "paper_2_path": paper2_path,
        "exp1_name": exp1_name,
        "exp2_name": exp2_name,
    }

    with FILE_LOCK:
        current_results_dict[paper_id] = result_entry
        with open(output_json_path, "w") as f:
            json.dump(current_results_dict, f, indent=4)

    print(
        f"✅ [{paper_id}] Finished rating SxS Overall Paper Quality (Double). 5pt: {category_5pt}, 3pt: {category_3pt}",
        flush=True,
    )
    return paper_id, True


def perform_sxs_paper_quality_batch(
    project_folder_1: str,
    project_folder_2: str,
    rel_path_1: str,
    rel_path_2: str,
    exp1_name: str,
    exp2_name: str,
    output_folder: str = "./logs/sxs_paper_quality",
    model_name: str = "gemini-3.1-pro-preview",
):
    print(f"Starting Enhanced SxS Paper Quality batch execution...", flush=True)
    print(f"Project 1: {project_folder_1} ({rel_path_1})", flush=True)
    print(f"Project 2: {project_folder_2} ({rel_path_2})", flush=True)
    print(f"Comparing [{exp1_name}] vs [{exp2_name}] using {model_name}", flush=True)

    os.makedirs(output_folder, exist_ok=True)
    conference = "unknown"
    if "iclr" in project_folder_1.lower():
        conference = "iclr"
    elif "cvpr" in project_folder_1.lower():
        conference = "cvpr"

    output_json_path = os.path.join(
        output_folder,
        f"sxs_paper_quality_enhanced_{model_name}_{exp1_name}_vs_{exp2_name}_{conference}.json",
    )

    current_results = {}
    if os.path.exists(output_json_path):
        with open(output_json_path, "r") as f:
            current_results = json.load(f)

    folder1_ids = [
        d
        for d in os.listdir(project_folder_1)
        if os.path.isdir(os.path.join(project_folder_1, d))
    ]
    folder2_ids = set(
        [
            d
            for d in os.listdir(project_folder_2)
            if os.path.isdir(os.path.join(project_folder_2, d))
        ]
    )

    common_ids = []
    for pid in folder1_ids:
        if pid in folder2_ids:
            p1 = os.path.join(project_folder_1, pid, rel_path_1)
            p2 = os.path.join(project_folder_2, pid, rel_path_2)
            if os.path.exists(p1) and os.path.exists(p2):
                if pid not in current_results:
                    common_ids.append((pid, p1, p2))
                else:
                    print(f"[{pid}] Already rated. Skipping.", flush=True)

    print(f"Found {len(common_ids)} overlapping papers to evaluate.", flush=True)

    max_workers = 3  # Reduced to avoid rate limits since we do 2 calls per paper
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = []
        for pid, p1, p2 in common_ids:
            f = executor.submit(
                _process_and_save_single_sxs,
                pid,
                p1,
                p2,
                output_json_path,
                current_results,
                model_name,
                exp1_name,
                exp2_name,
            )
            futures.append(f)

        for future in as_completed(futures):
            future.result()

    wins_5pt = 0
    leaning_wins_5pt = 0
    ties_5pt = 0
    leaning_losses_5pt = 0
    losses_5pt = 0

    wins_3pt = 0
    ties_3pt = 0
    losses_3pt = 0

    valid_evals = 0

    for pid, res in current_results.items():
        if pid == "_summary_stats":
            continue
        if not isinstance(res, dict) or "category_5pt" not in res:
            continue

        cat_5 = res["category_5pt"]
        cat_3 = res["category_3pt"]

        if cat_5 == "win":
            wins_5pt += 1
        elif cat_5 == "leaning_win":
            leaning_wins_5pt += 1
        elif cat_5 == "tie":
            ties_5pt += 1
        elif cat_5 == "leaning_loss":
            leaning_losses_5pt += 1
        elif cat_5 == "loss":
            losses_5pt += 1

        if cat_3 == "win":
            wins_3pt += 1
        elif cat_3 == "tie":
            ties_3pt += 1
        elif cat_3 == "loss":
            losses_3pt += 1

        valid_evals += 1

    stats = {
        "exp1_name": exp1_name,
        "exp2_name": exp2_name,
        "total_valid_evals": valid_evals,
        "five_point": {
            "wins": wins_5pt,
            "leaning_wins": leaning_wins_5pt,
            "ties": ties_5pt,
            "leaning_losses": leaning_losses_5pt,
            "losses": losses_5pt,
            "win_rate": wins_5pt / valid_evals if valid_evals > 0 else 0,
            "leaning_win_rate": (
                leaning_wins_5pt / valid_evals if valid_evals > 0 else 0
            ),
            "tie_rate": ties_5pt / valid_evals if valid_evals > 0 else 0,
        },
        "three_point": {
            "wins": wins_3pt,
            "ties": ties_3pt,
            "losses": losses_3pt,
            "win_rate": wins_3pt / valid_evals if valid_evals > 0 else 0,
            "tie_rate": ties_3pt / valid_evals if valid_evals > 0 else 0,
        },
    }

    current_results["_summary_stats"] = stats

    with open(output_json_path, "w") as f:
        json.dump(current_results, f, indent=4)

    print("\n" + "=" * 50, flush=True)
    print("ENHANCED SxS PAPER QUALITY EVALUATION SUMMARY", flush=True)
    print("=" * 50, flush=True)
    print(f"Total Evaluated: {valid_evals}", flush=True)
    print(f"--- 5-Point Scale ---", flush=True)
    print(
        f"[{exp1_name}] Wins: {wins_5pt} ({stats['five_point']['win_rate']:.1%})",
        flush=True,
    )
    print(
        f"[{exp1_name}] Leaning Wins: {leaning_wins_5pt} ({stats['five_point']['leaning_win_rate']:.1%})",
        flush=True,
    )
    print(f"Ties: {ties_5pt} ({stats['five_point']['tie_rate']:.1%})", flush=True)
    print(
        f"[{exp2_name}] Leaning Wins (P1 Lean Loss): {leaning_losses_5pt}", flush=True
    )
    print(f"[{exp2_name}] Wins (P1 Loss): {losses_5pt}", flush=True)
    print(f"--- 3-Point Scale ---", flush=True)
    print(
        f"[{exp1_name}] Wins: {wins_3pt} ({stats['three_point']['win_rate']:.1%})",
        flush=True,
    )
    print(f"Ties: {ties_3pt} ({stats['three_point']['tie_rate']:.1%})", flush=True)
    print(f"[{exp2_name}] Wins (P1 Loss): {losses_3pt}", flush=True)
    print("=" * 50 + "\n", flush=True)
    print(f"Batch completed. Results saved to {output_json_path}", flush=True)
