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

import re
import os
import requests
import json
import time
import os.path as osp
from typing import List, Dict, Any
from joblib import Parallel, delayed  # type: ignore
from tqdm import tqdm

import concurrent.futures
from threading import Lock

from utils.pdf_utils import get_paper_references_from_pdf, load_paper
from utils.common_utils import create_log_folder
from utils.content_parsing_utils import extract_paper_title_from_citation
from utils.llm_backend_utils import call_llm_with_text_prompt

from dotenv import load_dotenv  # type: ignore

dot_file = os.path.join(os.path.dirname(__file__), "../.env")
load_dotenv(dot_file)

DATASET_DIR = os.path.join(os.path.dirname(__file__), "../datasets")

S2_API_KEY = os.getenv("SEMANTIC_SCHOLAR_API_KEY")
print(f"Loaded S2 API Key for this project: {S2_API_KEY}")

PRIORITY_PROMPT = """You are an expert academic reviewer. Read the following paper text and analyze its references.
Your goal is to categorize the provided references into two priorities:
- P0 (Must-Have): Core citations strictly necessary for the paper. These MUST include:
    * Baselines directly compared against in experiments
    * Datasets the paper utilizes or evaluates on
    * Core methods the paper is directly building upon or modifying
    * Metrics or standard numbers heavily relied upon and cited from another paper
- P1 (Good-To-Have): Supplemental citations. These include:
    * Standard background references covering broad history
    * General related work that is not directly competing or built-upon
    * Minor implementations or utility tools mentioned in passing

PAPER TEXT:
{paper_text}

REFERENCES LIST:
{references_str}

Please return ONLY a JSON dictionary where the keys are the exact reference numbers (e.g., "1", "2") and the values are either "P0" or "P1".
Example output:

```json
{{
    "1": "P0",
    "2": "P1",
    "3": "P0"
}}
```
"""


class ReferenceF1V1Evaluator:
    def __init__(
        self,
        api_key: str = S2_API_KEY,
        log_folder: str = None,
        model_name: str = "gemini-3.1-pro-preview",
    ):
        # Semantic Scholar API endpoint
        self.S2_SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
        self.headers = {"X-API-KEY": api_key} if api_key else {}
        self.model_name = model_name

        if not log_folder:
            log_folder = create_log_folder(prefix="citation_autorater")
        self.log_folder = log_folder

    def _clean_text_to_list(self, raw_text: str) -> tuple[List[str], List[str]]:
        """
        Parses the raw string containing [1]...[2]... into a list of citation strings.
        """
        pattern = r"\[\d+\]"
        segments = re.split(pattern, raw_text)

        cleaned_refs = [
            seg.strip().replace("\n", " ").replace("  ", " ")
            for seg in segments
            if seg.strip()
        ]

        # Parallel extraction of titles from citation strings
        cleaned_titles = Parallel(n_jobs=10, backend="threading")(
            delayed(extract_paper_title_from_citation)(ref)
            for ref in tqdm(cleaned_refs, desc="Extracting Titles from Text")
        )

        return cleaned_refs, cleaned_titles

    def _fetch_paper_id(self, paper_title: str) -> dict:
        """
        Queries Semantic Scholar with the raw citation string to find a Unique ID (paperId).
        """
        if not paper_title:
            return None

        params = {"query": paper_title, "limit": 1, "fields": "paperId,title"}

        try:
            response = requests.get(
                self.S2_SEARCH_URL, headers=self.headers, params=params, timeout=20
            )

            if response.status_code == 200:
                data = response.json()
                if data["total"] > 0 and data["data"]:
                    return {
                        "fetched_paper_id": data["data"][0]["paperId"],
                        "fetched_paper_title": data["data"][0]["title"],
                    }
            elif response.status_code == 429:
                print("Rate limit hit. Sleeping for 2 seconds...")
                time.sleep(2)
                return self._fetch_paper_id(paper_title)

        except Exception as e:
            print(f"Error fetching ID for ref: {paper_title}... -> {e}")

        return None

    def _get_ids_for_ref_list(self, ref_list: List[str], filler: str = "-1"):
        """
        Batch processes a list of strings into a set of unique IDs.
        """
        ids_set = set()
        ids_list = []
        titles_list = []
        print(f"Processing {len(ref_list)} references via S2 API...")

        for ref in tqdm(ref_list, desc="Resolving IDs"):
            fetched_info = self._fetch_paper_id(ref)
            pid = fetched_info["fetched_paper_id"] if fetched_info else None
            fetched_title = (
                fetched_info["fetched_paper_title"] if fetched_info else None
            )

            if pid:
                ids_set.add(pid)
                ids_list.append(pid)
                titles_list.append(fetched_title)
            else:
                ids_list.append(filler)
                titles_list.append(filler)

            time.sleep(0.5)

        return ids_set, ids_list, titles_list

    def _get_citation_priorities(
        self, paper_text: str, cleaned_refs: List[str]
    ) -> Dict[str, str]:
        """
        Uses LLM to classify references into P0 or P1.
        """

        references_str = "\n".join(
            [f"[{i+1}] {ref}" for i, ref in enumerate(cleaned_refs)]
        )

        prompt = PRIORITY_PROMPT.format(
            paper_text=paper_text, references_str=references_str
        )
        try:
            output = call_llm_with_text_prompt(
                prompt=prompt,
                model_name=self.model_name,
                generation_configs={"temperature": 0.0},
            )
            parsed_priorities = output.get("parsed_response", {})
            if not parsed_priorities:
                print("Warning: LLM returned empty or invalid priority JSON.")
            return parsed_priorities
        except Exception as e:
            print(f"Error calling LLM for priorities: {e}")
            return {}

    def process_text_to_data(
        self, raw_text: str, tag: str = "na", paper_text: str = None
    ) -> Dict[str, Any]:
        """
        Orchestrates cleaning text and fetching IDs.
        If paper_text is provided, uses LLM to assign P0/P1 priorities.
        Returns a serializable dictionary.
        """
        ref_list, ref_titles = self._clean_text_to_list(raw_text)

        filler_val = f"{tag}_NA"
        ids_set, ids_list, fetched_titles = self._get_ids_for_ref_list(
            ref_titles, filler=filler_val
        )

        priorities = {}
        if paper_text is not None:
            print("Calling LLM to classify citation priorities...")
            # Map 1-indexed strictly to the extracted ref_list length
            start_llm = time.time()
            priorities = self._get_citation_priorities(paper_text, ref_list)
            end_llm = time.time()
            print(f"Finished Calling LLM. Took {end_llm - start_llm:.2f} seconds.")

        # Structure the citation info for logging/debugging
        citation_info = []
        p0_ids = set()
        p1_ids = set()

        for idx in range(len(ref_list)):
            priority = (
                priorities.get(str(idx + 1), "P1") if priorities else "P1"
            )  # Default to P1 if no priority provided or missing

            pid = ids_list[idx]
            if pid and pid != filler_val:
                if priority == "P0":
                    p0_ids.add(pid)
                    if pid in p1_ids:
                        p1_ids.remove(pid)  # P0 takes precedence
                else:
                    if pid not in p0_ids:
                        p1_ids.add(pid)

            citation_info.append(
                {
                    "citation_text": ref_list[idx],
                    "extracted_paper_title": ref_titles[idx],
                    "fetched_paper_id": pid,
                    "fetched_paper_title": fetched_titles[idx],
                    "priority": priority,
                }
            )

        return {
            "citation_info": citation_info,
            "all_ids": list(ids_set),
            "all_ids_count": len(ids_set),
            "p0_ids": list(p0_ids),
            "p0_ids_count": len(p0_ids),
            "p1_ids": list(p1_ids),
            "p1_ids_count": len(p1_ids),
        }

    def evaluate_from_data(self, gt_data: Dict, gen_data: Dict) -> Dict:
        """
        Computes precision/recall/f1 using pre-processed dictionary data for Overall, P0, and P1.
        """
        log_path_gt = os.path.join(self.log_folder, "gt_ref_info.json")
        with open(log_path_gt, "w") as f:
            json.dump(gt_data, f, indent=4)

        log_path_gen = os.path.join(self.log_folder, "gen_ref_info.json")
        with open(log_path_gen, "w") as f:
            json.dump(gen_data, f, indent=4)

        gt_ids_all = set(gt_data.get("all_ids", []))
        gt_ids_p0 = set(gt_data.get("p0_ids", []))
        gt_ids_p1 = set(gt_data.get("p1_ids", []))

        # Fallback extraction if older cache doesn't have p0_ids list directly
        if not gt_ids_p0 and not gt_ids_p1 and "citation_info" in gt_data:
            gt_ids_all = set()
            for item in gt_data.get("citation_info", []):
                pid = item["fetched_paper_id"]
                if pid and pid != "gt_NA":
                    gt_ids_all.add(pid)
                    if item.get("priority") == "P0":
                        gt_ids_p0.add(pid)
                        if pid in gt_ids_p1:
                            gt_ids_p1.remove(pid)
                    else:
                        if pid not in gt_ids_p0:
                            gt_ids_p1.add(pid)

        # Still fallback to pairwise if cache is old
        elif not gt_ids_p0 and not gt_ids_p1 and "pairwise" in gt_data:
            gt_ids_all = set()
            for item in gt_data.get("pairwise", []):
                pid = item["fetched_paper_id"]
                if pid and pid != "gt_NA":
                    gt_ids_all.add(pid)
                    if item.get("priority") == "P0":
                        gt_ids_p0.add(pid)
                        if pid in gt_ids_p1:
                            gt_ids_p1.remove(pid)
                    else:
                        if pid not in gt_ids_p0:
                            gt_ids_p1.add(pid)

        gen_ids_all = set(gen_data.get("all_ids", []))
        gen_ids_all = {pid for pid in gen_ids_all if pid and pid != "gen_NA"}

        print("-" * 50)
        print(f"Ground Truth Unique IDs (All): {len(gt_ids_all)}")
        print(f"Ground Truth Unique IDs (P0):  {len(gt_ids_p0)}")
        print(f"Ground Truth Unique IDs (P1):  {len(gt_ids_p1)}")
        print(f"Generated Unique IDs:          {len(gen_ids_all)}")

        tp_overall = len(gen_ids_all.intersection(gt_ids_all))
        gen_count = len(gen_ids_all)
        gt_count = len(gt_ids_all)
        gt_p0_count = len(gt_ids_p0)
        gt_p1_count = len(gt_ids_p1)

        tp_p0 = len(gen_ids_all.intersection(gt_ids_p0))
        tp_p1 = len(gen_ids_all.intersection(gt_ids_p1))

        overall_precision = tp_overall / gen_count if gen_count > 0 else 0.0
        overall_recall = tp_overall / gt_count if gt_count > 0 else 0.0
        overall_f1 = (
            2
            * (overall_precision * overall_recall)
            / (overall_precision + overall_recall)
            if (overall_precision + overall_recall) > 0
            else 0.0
        )

        p0_recall = tp_p0 / gt_p0_count if gt_p0_count > 0 else 0.0
        p1_recall = tp_p1 / gt_p1_count if gt_p1_count > 0 else 0.0

        metrics_dict = {
            "overall_precision": overall_precision,
            "overall_recall": overall_recall,
            "overall_f1": overall_f1,
            "p0_recall": p0_recall,
            "p1_recall": p1_recall,
            "counts": {
                "ground_truth_ids_all": gt_count,
                "ground_truth_ids_p0": gt_p0_count,
                "ground_truth_ids_p1": gt_p1_count,
                "generated_ids_all": gen_count,
                "matches_overall": tp_overall,
                "matches_p0": tp_p0,
                "matches_p1": tp_p1,
            },
        }

        output_json_path = os.path.join(self.log_folder, "metrics.json")
        with open(output_json_path, "w") as f:
            json.dump(metrics_dict, f, indent=4)
        print(f"Dumped metrics to {output_json_path}.")

        return metrics_dict


def get_citation_f1_metrics(
    original_pdf: str,
    generated_pdf: str,
    log_folder=None,
    gt_cache_path: str = None,
    model_name: str = "gemini-3.1-pro-preview",
):
    """
    Computes priority-based citation F1. Caches Ground Truth processing to avoid redundant LLM/API calls.
    """
    evaluator = ReferenceF1V1Evaluator(log_folder=log_folder, model_name=model_name)

    # --- 1. Handle Ground Truth (With Caching) ---
    if not gt_cache_path:
        gt_cache_path = (
            os.path.splitext(original_pdf)[0] + f"_gt_citations_{model_name}.json"
        )
    print(f"Using GT cache path: {gt_cache_path}")

    gt_data = None
    if os.path.exists(gt_cache_path):
        print(f"Loading cached Ground Truth references from: {gt_cache_path}")
        try:
            with open(gt_cache_path, "r") as f:
                gt_data = json.load(f)
        except Exception as e:
            print(f"Failed to load cache {gt_cache_path}, will re-process. Error: {e}")

    if gt_data is None:
        print(f"Processing Ground Truth PDF: {original_pdf}")
        gt_references_text = get_paper_references_from_pdf(
            original_pdf, model_name=model_name
        )
        if gt_references_text is None:
            print("Error: Could not extract text from GT PDF.")
            gt_references_text = ""

        print(f"Loading full paper text for LLM citation categorization...")
        paper_text = load_paper(
            original_pdf, num_pages=20
        )  # Limit to 20 pages to save token limit context if needed, though pro can handle more

        gt_data = evaluator.process_text_to_data(
            gt_references_text, tag="gt", paper_text=paper_text
        )

        try:
            with open(gt_cache_path, "w") as f:
                json.dump(gt_data, f, indent=4)
            print(f"Cached Ground Truth references to: {gt_cache_path}")
        except Exception as e:
            print(f"Warning: Could not write GT cache file. {e}")

    # --- 2. Handle Generated PDF (Always Process) ---
    print(f"Processing Generated PDF: {generated_pdf}")
    gen_references_text = get_paper_references_from_pdf(
        generated_pdf, model_name=model_name
    )
    if gen_references_text is None:
        print("Error: Could not extract text from Generated PDF.")
        gen_references_text = ""

    gen_data = evaluator.process_text_to_data(gen_references_text, tag="gen")

    # --- 3. Compare ---
    results = evaluator.evaluate_from_data(gt_data, gen_data)

    print(f"\n--- Overall Metrics ---")
    print(f"Overall Precision: {results['overall_precision']:.2f}")
    print(f"Overall Recall:    {results['overall_recall']:.2f}")
    print(f"Overall F1 Score:  {results['overall_f1']:.2f}")

    print(f"\n--- Priority Recall Metrics ---")
    print(f"P0 Recall:         {results['p0_recall']:.2f}")
    print(f"P1 Recall:         {results['p1_recall']:.2f}")

    return results


def generate_gt_citations_batch(
    base_folder: str,
    sub_folder_name: str,
    progress_json_path: str = None,
    max_workers: int = 5,
    evaluator_log_folder: str = None,
    model_name: str = "gemini-3.1-pro-preview",
):
    """
    Given a folder of papers (e.g., cvpr2025), iterates through its subfolders.
    For each paper folder, it checks a specific subfolder (e.g., "raw_materials")
    and generates 'original_paper_gt_citations_{model_name}.json' inside it based on the original PDF.
    It utilizes the LLM to prioritize the GT citations (P0/P1).
    It also updates '{base_folder}/info.json' with 'num_gt_citations_p0' and 'num_gt_citations_p1'.
    It tracks successful processing in an optional `progress_json_path`.
    """
    if not os.path.exists(base_folder):
        print(f"Error: Base folder '{base_folder}' does not exist.")
        return

    evaluator_lock = Lock()
    evaluator = ReferenceF1V1Evaluator(
        log_folder=evaluator_log_folder, model_name=model_name
    )

    # Load info.json if it exists
    info_json_path = os.path.join(base_folder, "info.json")
    info_data = []
    info_map = {}
    if os.path.exists(info_json_path):
        try:
            with open(info_json_path, "r") as f:
                info_data = json.load(f)
            if isinstance(info_data, list):
                for item in info_data:
                    if "paper_id" in item:
                        info_map[item["paper_id"]] = item
        except Exception as e:
            print(f"Warning: Could not read {info_json_path}: {e}")

    info_map_lock = Lock()

    # Progress tracking setup
    progress_data = {"processed_count": 0, "successful_papers": {}}
    if progress_json_path and os.path.exists(progress_json_path):
        try:
            with open(progress_json_path, "r") as f:
                progress_data = json.load(f)
                print(f"Loaded existing progress from {progress_json_path}")
        except Exception as e:
            print(f"Warning: Could not load existing progress: {e}")

    progress_lock = Lock()

    def _save_progress():
        if progress_json_path:
            with progress_lock:
                try:
                    with open(progress_json_path, "w") as f:
                        json.dump(progress_data, f, indent=4)
                except Exception as e:
                    print(f"Error saving progress: {e}")

    paper_folders = [
        f
        for f in os.listdir(base_folder)
        if os.path.isdir(os.path.join(base_folder, f))
    ]
    print(f"Found {len(paper_folders)} folders in {base_folder}")

    def process_single_paper(paper_num: str):
        paper_path = os.path.join(base_folder, paper_num)
        target_subfolder = os.path.join(paper_path, sub_folder_name)

        if not os.path.exists(target_subfolder):
            print(f"Skipping {paper_num}: Subfolder '{sub_folder_name}' not found.")
            return

        pdf_files = [f for f in os.listdir(paper_path) if f.endswith(".pdf")]
        target_pdf_name = f"{paper_num}.pdf"

        pdf_path = None
        if target_pdf_name in pdf_files:
            pdf_path = os.path.join(paper_path, target_pdf_name)
        elif len(pdf_files) > 0:
            pdf_path = os.path.join(paper_path, pdf_files[0])
            print(
                f"Warning: Exact PDF {target_pdf_name} not found. Using {pdf_files[0]} instead."
            )
        else:
            print(f"Skipping {paper_num}: No PDF found in {paper_path}")
            return

        output_json_path = os.path.join(
            target_subfolder, f"original_paper_gt_citations_{model_name}.json"
        )

        gt_data = None
        if os.path.exists(output_json_path):
            print(f"Skipping {paper_num}: {output_json_path} already exists.")
            try:
                with open(output_json_path, "r") as f:
                    gt_data = json.load(f)

                # Update progress since it exists
                with progress_lock:
                    if paper_num not in progress_data["successful_papers"]:
                        progress_data["successful_papers"][paper_num] = output_json_path
                        progress_data["processed_count"] = len(
                            progress_data["successful_papers"]
                        )
                _save_progress()
            except Exception as e:
                print(f"Error reading existing json {output_json_path}: {e}")
        else:
            print(f"\n[{paper_num}] Processing {pdf_path}...")
            try:
                # Extract text (thread-safe operations)
                print(f"[{paper_num}] Starting get_paper_references_from_pdf...")
                gt_references_text = get_paper_references_from_pdf(
                    pdf_path, model_name=model_name
                )
                print(f"[{paper_num}] Finished get_paper_references_from_pdf.")

                if gt_references_text is None:
                    print(f"Error: Could not extract text from {pdf_path}")
                    return

                print(
                    f"[{paper_num}] Loading full paper text for LLM citation categorization..."
                )
                paper_text = load_paper(pdf_path, min_size=100)
                print(f"[{paper_num}] Finished loading full paper text.")

                # Evaluate and API calls (Use lock to be safe from rate limit races if needed)
                print(f"[{paper_num}] Waiting for evaluator_lock...")
                with evaluator_lock:
                    print(
                        f"[{paper_num}] Acquired evaluator_lock. Starting process_text_to_data..."
                    )
                    gt_data = evaluator.process_text_to_data(
                        gt_references_text, tag="gt", paper_text=paper_text
                    )
                    print(f"[{paper_num}] Finished process_text_to_data.")
                print(f"[{paper_num}] Released evaluator_lock.")

                with open(output_json_path, "w") as f:
                    json.dump(gt_data, f, indent=4)

                print(f"Successfully generated {output_json_path}")

                # Update progress after successful generation
                with progress_lock:
                    progress_data["successful_papers"][paper_num] = output_json_path
                    progress_data["processed_count"] = len(
                        progress_data["successful_papers"]
                    )
                _save_progress()

            except Exception as e:
                print(f"Error processing {paper_num}: {e}")

        # Update info.json mapping securely
        if gt_data is not None:
            p0_count = gt_data.get("p0_ids_count", 0)
            p1_count = gt_data.get("p1_ids_count", 0)

            # Fallback for old cache
            if "citation_info" in gt_data and "p0_ids_count" not in gt_data:
                p0_count = 0
                p1_count = 0
                for item in gt_data.get("citation_info", []):
                    if item.get("priority") == "P0":
                        p0_count += 1
                    else:
                        p1_count += 1
            elif "pairwise" in gt_data:
                p0_count = 0
                p1_count = 0
                for item in gt_data.get("pairwise", []):
                    if item.get("priority") == "P0":
                        p0_count += 1
                    else:
                        p1_count += 1

            with info_map_lock:
                if paper_num in info_map:
                    info_map[paper_num]["num_gt_citations_p0"] = p0_count
                    info_map[paper_num]["num_gt_citations_p1"] = p1_count

    # Run the processing in parallel
    print(f"Starting parallel processing with {max_workers} thread workers...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        list(
            tqdm(
                executor.map(process_single_paper, paper_folders),
                total=len(paper_folders),
                desc="Parallel Processing Papers",
            )
        )

    # Save info.json back out if it existed
    if os.path.exists(info_json_path) and isinstance(info_data, list):
        updated_info_data = []
        for item in info_data:
            if "paper_id" in item and item["paper_id"] in info_map:
                updated_info_data.append(info_map[item["paper_id"]])
            else:
                updated_info_data.append(item)

        try:
            with open(info_json_path, "w") as f:
                json.dump(updated_info_data, f, indent=4)
            print(f"Successfully updated {info_json_path} with P0/P1 citation counts.")
        except Exception as e:
            print(f"Error saving updated {info_json_path}: {e}")


def review_citation_f1_batch(
    project_folder: str,
    output_folder: str = None,
    gen_paper_rel_path: str = "latex_writeup/final_paper.pdf",
    max_workers: int = 5,
    model_name: str = "gemini-3.1-pro-preview",
):
    all_results = {}
    all_results_dump_path = os.path.join(
        project_folder, f"citation_f1_results_{model_name}.json"
    )

    if os.path.exists(all_results_dump_path):
        with open(all_results_dump_path, "r") as f:
            all_results = json.load(f)
            print(f"Loaded {len(all_results)-1} results from {all_results_dump_path}.")

    paper_id_list = os.listdir(project_folder)
    cleaned_paper_id_list = []
    for paper_id in paper_id_list:
        if not os.path.isdir(os.path.join(project_folder, paper_id)):
            continue
        if not os.path.exists(
            os.path.join(project_folder, paper_id, gen_paper_rel_path)
        ):
            continue
        cleaned_paper_id_list.append(paper_id)
    paper_id_list = cleaned_paper_id_list

    results_lock = Lock()

    def process_review_paper(paper_id: str):
        try:
            with results_lock:
                if paper_id in all_results:
                    print(f"Skipping already processed paper '{paper_id}'.")
                    return

            paper_folder = os.path.join(project_folder, paper_id)
            if not os.path.isdir(paper_folder):
                return

            paper_log_folder = os.path.join(paper_folder, "citation_f1_metrics")
            os.makedirs(paper_log_folder, exist_ok=True)

            print(f"[{paper_id}] Processing paper...")

            data = {}
            data["paper_id"] = paper_id
            os.makedirs(paper_folder, exist_ok=True)

            original_pdf_path = os.path.join(
                paper_folder, "raw_materials/original_paper.pdf"
            )
            if not os.path.exists(original_pdf_path):
                if "cvpr2025" in project_folder.lower():
                    original_pdf_path = os.path.join(
                        DATASET_DIR, "cvpr2025/papers/{paper_id}/{paper_id}.pdf"
                    )
                elif "iclr2025" in project_folder.lower():
                    original_pdf_path = os.path.join(
                        DATASET_DIR, "iclr2025/papers/{paper_id}/{paper_id}.pdf"
                    )
                else:
                    raise ValueError(f"Unknown dataset: {project_folder}")

            gen_pdf_path = os.path.join(paper_folder, gen_paper_rel_path)

            # Define where the GT cache should live specifically to avoid race conditions
            # or missing files
            gt_cache_path = os.path.join(
                paper_folder,
                "raw_materials",
                f"original_paper_gt_citations_{model_name}.json",
            )

            result_metrics = get_citation_f1_metrics(
                original_pdf=original_pdf_path,
                generated_pdf=gen_pdf_path,
                log_folder=paper_log_folder,
                gt_cache_path=gt_cache_path,
                model_name=model_name,
            )

            data["real_pdf_path"] = original_pdf_path
            data["generated_pdf_path"] = gen_pdf_path
            data["metrics"] = result_metrics

            with results_lock:
                all_results[paper_id] = data
                with open(all_results_dump_path, "w") as f:
                    json.dump(all_results, f, indent=4)

        except Exception as e:
            print(f"Error processing paper '{paper_id}': {e}")
            return

    print(f"Starting parallel review execution with {max_workers} thread workers...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        list(
            tqdm(
                executor.map(process_review_paper, paper_id_list),
                total=len(paper_id_list),
                desc="Parallel Reviewing Papers",
            )
        )

    with open(all_results_dump_path, "w") as f:
        json.dump(all_results, f, indent=4)

    print(f"Dumped {len(all_results)} results to {all_results_dump_path}.")

    # Run and append overall metrics
    analyze_citation_metrics(all_results_dump_path)

    return all_results


def analyze_citation_metrics(json_file_path: str):
    if not os.path.exists(json_file_path):
        print(f"Error: File not found: {json_file_path}")
        return

    with open(json_file_path, "r") as f:
        json_data = json.load(f)

    # Metrics we want to track
    # Main metrics (0-1 range)
    score_keys = [
        "overall_precision",
        "overall_recall",
        "overall_f1",
        "p0_recall",
        "p1_recall",
    ]

    # Count metrics (integers)
    count_keys = [
        "ground_truth_ids_all",
        "ground_truth_ids_p0",
        "ground_truth_ids_p1",
        "generated_ids_all",
        "matches_overall",
        "matches_p0",
        "matches_p1",
    ]

    sums = {key: 0.0 for key in score_keys}
    count_sums = {key: 0.0 for key in count_keys}

    valid_papers_count = 0

    print(f"Loading data from {json_file_path}...")

    for paper_id, data in json_data.items():
        if paper_id == "overall_metrics":
            continue

        metrics = data.get("metrics")
        if not metrics:
            continue

        valid_papers_count += 1

        for key in score_keys:
            sums[key] += metrics.get(key, 0.0)

        counts_dict = metrics.get("counts", {})
        for key in count_keys:
            count_sums[key] += counts_dict.get(key, 0)

    if valid_papers_count == 0:
        print("No papers found with metrics.")
        return

    print(f"\nAggregated Results over {valid_papers_count} papers:")
    print("=" * 60)

    print(f"{'Metric':<30} | {'Average':<10}")
    print("-" * 60)

    overall_metrics = {}

    for key in score_keys:
        avg = sums[key] / valid_papers_count
        label = key.replace("_", " ").title()
        print(f"{label:<30} | {avg:.4f}")
        overall_metrics[key] = avg

    print("-" * 60)
    overall_metrics["counts"] = {}
    for key in count_keys:
        avg = count_sums[key] / valid_papers_count
        label = key.replace("_", " ").title()
        print(f"{label:<30} | {avg:.2f}")
        overall_metrics["counts"][key] = avg

    print("=" * 60)

    json_data["overall_metrics"] = overall_metrics
    with open(json_file_path, "w") as f:
        json.dump(json_data, f, indent=4)
