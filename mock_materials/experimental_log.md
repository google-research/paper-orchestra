## 1. Experimental Setup

We conducted a comprehensive evaluation of the proposed TSAM method for the Referring Audio-Visual Segmentation (Ref-AVS) task.

*   **Datasets:**
    *   **Ref-AVS Dataset:** We utilized the Ref-AVS dataset containing 20,000 text expressions and pixel-level annotations across 4,000 10-second videos.
    *   **Object Categories:** The dataset included audible objects (20 musical instruments, 8 animals, 15 machines, 5 humans) and 3 categories of static, inaudible objects.
    *   **Splits:**
        *   **Training Set:** 2,908 videos.
        *   **Validation Set:** 276 videos.
        *   **Test Set:** 818 videos total, subdivided into:
            *   *Seen:* 292 videos (categories present in training).
            *   *Unseen:* 269 videos (categories not seen during training; tests generalization).
            *   *Null:* 257 videos (text refers to non-existent/not visible objects; empty true masks).

*   **Evaluation Metrics:**
    *   **Standard Metrics:** We employed the Jaccard Index ($_mathcal{J}$) and F-score ($_mathcal{F}$) for the Seen and Unseen subsets.
    *   **Null Subset Metric:** We employed the metric $_mathcal{S}$, which measures the ratio of the predicted mask area to the background area ($_mathcal{S} = \sqrt{	ext{predicted mask area} / 	ext{background area}}$). A lower $_mathcal{S}$ value indicates better performance (less incorrect segmentation).

 Baselines Compared:**
    *   **AVS Methods (Augmented with Text):** AVSBench (PVT-v2 backbone), AVSegFormer (PVT-v2 backbone), GAVS (SAM backbone), SAMA (SAM backbone). *Note: We re-evaluated SAMA by integrating text with audio/visual inputs.*
    *   **Ref-VOS Methods (Augmented with Audio):** ReferFormer (Video-Swin backbone), R2-VOS (Video-Swin backbone).
    *   **Ref-AVS Method:** EEMC (Mask2Former backbone; previous state-of-the-art).

*   **Implementation Details:**
    *   **Model Initialization:** We initialized TSAM using the pre-trained ViT-B variant of SAM ($N=12$, embedding dimension $d_{emb}=256$).
    *   **Architecture Settings:** The temporal branch consisted of $M=4$ blocks. The number of selected audio queries was set to $k=5$.
    *   **Hardware:** Training was performed on eight AMD GPUs in a distributed setup.
    *   **Optimizer:** AdamW optimizer was used.
    *   **Hyperparameters:** Initial learning rate of $1 \cdot 10^{-4}$, batch size of 1.
    *   **Training Duration:** The model was trained for 15 epochs with periodic evaluations.
    *   **Model Selection:** We selected the best-performing model on the validation subset for testing.

## 2. Raw Numeric Data

**Table 1: Performance comparison on the Ref-AVS dataset**
*Note: Baselines marked with † had text integration added; baselines marked with ‡ had audio integration added; * marks our re-implementation of SAMA with text added.*

| Method | Task | Visual Backbone | Seen J(%) | Seen F | Unseen J(%) | Unseen F | Null S(↓) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| AVSBench | AVS† | PVT-v2 | 23.20 | 0.511 | 32.36 | 0.547 | 0.208 |
| AVSegFormer | AVS† | PVT-v2 | 33.47 | 0.470 | 36.05 | 0.501 | 0.171 |
| GAVS | AVS† | SAM | 28.93 | 0.498 | 29.82 | 0.497 | 0.190 |
| SAMA | AVS* | SAM | 39.22 | 0.562 | 47.50 | 0.566 | 0.130 |
| ReferFormer | Ref-VOS‡ | V-Swin | 31.31 | 0.501 | 30.40 | 0.488 | 0.176 |
| R2-VOS | Ref-VOS‡ | V-Swin | 25.01 | 0.410 | 27.93 | 0.498 | 0.183 |
| EEMC | Ref-AVS | M2F | 34.20 | 0.513 | 49.54 | 0.648 | **0.007** |
| **TSAM (Ours)** | Ref-AVS | SAM | **43.43** | **0.568** | **54.58** | **0.664** | 0.017 |

**Table 2: Ablation study on TSAM components and IoU loss**
*Legend: TB=Temporal Branch, TMFL=Temporal Modality Fusion Layer, DPM=Dense Prompting Module, SPM=Sparse Prompting Module, CM=Cached Memory, AM=Adapter Module. Mix(S+U) is the average of Seen and Unseen.*

| Setting | Seen J(%) | Seen F | Unseen J(%) | Unseen F | Mix(S+U) J(%) | Mix(S+U) F | Null S(↓) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| ① TSAM (Full) | **43.43** | 0.568 | **54.58** | **0.664** | **49.01** | **0.616** | 0.017 |
| ② - TB | 33.05 | 0.507 | 50.48 | 0.657 | 41.77 | 0.582 | 0.505 |
| ③ - TMFL | 40.35 | 0.579 | 45.54 | 0.627 | 42.95 | 0.603 | 0.018 |
| ④ - DPM | 42.72 | 0.580 | 49.10 | 0.647 | 45.91 | 0.614 | 0.018 |
| ⑤ - SPM | 43.04 | 0.580 | 49.75 | 0.652 | 46.40 | **0.616** | 0.018 |
| ⑥ - SPM+DPM | 42.60 | 0.602 | 40.58 | 0.604 | 41.59 | 0.603 | 0.018 |
| ⑦ - CM(a+v) | 42.07 | 0.544 | 49.11 | 0.659 | 45.59 | 0.602 | 0.018 |
| ⑧ - CM(v) | 42.75 | 0.549 | 51.18 | 0.660 | 46.97 | 0.605 | 0.018 |
| ⑨ - AM | 43.13 | **0.600** | 40.79 | 0.617 | 41.96 | 0.609 | 0.017 |
| ⑩ - $_mathcal{L}_{IoU}$ | 38.29 | 0.564 | 42.15 | 0.631 | 40.22 | 0.598 | **0.008** |

**Table 3: Effect of audio queries ($k$) and temporal branch depth ($M$)**

| Variation | Seen J(%) | Seen F | Unseen J(%) | Unseen F | Mix(S+U) J(%) | Mix(S+U) F | Null S(↓) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **$k=3$** | 43.58 | **0.579** | 50.43 | 0.655 | 47.01 | **0.617** | 0.018 |
| **$k=5$** | 43.43 | 0.568 | **54.58** | **0.664** | **49.01** | 0.616 | **0.017** |
| **$k=7$** | 43.24 | 0.573 | 46.95 | 0.630 | 45.10 | 0.601 | 0.018 |
| **$M=2$** | 42.04 | 0.566 | 53.51 | 0.651 | 47.76 | 0.609 | 0.023 |
| **$M=4$** | **43.43** | 0.568 | **54.58** | **0.664** | **49.01** | **0.616** | **0.017** |
| **$M=6$** | 43.27 | **0.575** | 49.86 | 0.640 | 46.57 | 0.608 | 0.020 |

## 3. Qualitative Observations

**Comparisons with State-of-the-Art:**
*   **Backbone Analysis:** We observed that methods utilizing prior segmentation visual backbones (SAM and Mask2Former) generally outperformed those based on PVT-v2 and V-Swin backbones.
*   **SAM-Based Baseline Limitations:** Although GAVS and SAMA are SAM-based, they performed worse than EEMC. We noted that SAMA failed to leverage SAM's flexible, promptable nature, and GAVS lacked cohesive multimodal fusion.
*   **TSAM Performance:** TSAM achieved the highest performance on both Seen and Unseen test sets. Specifically, TSAM improved over EEMC by 9.23% in Jaccard Index on the Seen set and 5.04% on the Unseen set.
*   **Null Set Performance:** TSAM fell slightly behind EEMC on the Null test set (S value 0.017 vs 0.007). We attribute this to SAM's inherent limitation of always attempting to produce a segmentation mask even when no target object is present.

**Ablation Observations:**
*   **Temporal Branch (TB):** Removing the temporal branch caused the most significant performance degradation (Seen Jaccard dropped from 43.43% to 33.05%). This confirmed the critical role of temporal modeling for generalizing across video frames.
*   **Prompting Modules (SPM/DPM):** We found that the Sparse Prompting Module (SPM) and Dense Prompting Module (DPM) play complementary roles. Removing both simultaneously resulted in a notable decrease in segmentation performance.
*   **Cached Memory (CM):** Omitting cached memory, especially the visual-only memory, degraded performance, highlighting the importance of shared memory for temporal alignment.
*   **Adapter Module (AM):** The omission of the adapter module caused a significant performance drop, particularly on the Unseen test set, validating its role in facilitating deep multimodal interaction.
*   **Loss Function:** Including the IoU loss ($_mathcal{L}_{IoU}$) improved performance on Seen and Unseen sets but slightly degraded the Null score.

**Hyperparameter Sensitivity:**
*   **Audio Queries ($k$):** We found that $k=5$ yielded optimal results. A lower value ($k=3$) performed well on Seen data but worse on Unseen, while a higher value ($k=7$) likely introduced irrelevant queries, overloading the decoder.
*   **Temporal Depth ($M$):** $M=4$ blocks provided the best balance. Shallower setups ($M=2$) lacked sufficient temporal depth, while deeper setups ($M=6$) appeared to introduce excessive complexity that impaired generalization.

**Visual Qualitative Analysis:**
*   **Seen Test Set:** We observed that TSAM consistently produced high-quality masks for targeted objects. It successfully segmented inaudible objects when guided by textual cues (e.g., "The object behind the sounding women"), demonstrating effective processing of complex multimodal instructions.
*   **Unseen Test Set:** TSAM demonstrated a remarkable capacity to generalize to novel objects. It effectively aligned audio-visual and textual inputs in novel scenes (e.g., segmenting a "truck moving" or "tuba being played" that were not in training categories).
*   **Generalization:** The visual results underscored TSAM's ability to preserve SAM's pre-trained knowledge while using the temporal branch to understand dynamic scenes.