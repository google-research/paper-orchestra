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

import streamlit as st
import os
import json
import sys
import time
import threading
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from dotenv import load_dotenv
import subprocess
import shutil
import tempfile
import datetime
import io
import zipfile
from streamlit.runtime.scriptrunner import add_script_run_ctx
import signal
import ctypes
from frontend_utils import send_notification_email

load_dotenv()

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from methods.paper_writer import write_single_paper
from utils.pdf_utils import pdf_to_grid_images

st.set_page_config(
    page_title="Paper Orchestra - AI Paper Writer",
    page_icon="🎻",
    layout="wide",
    initial_sidebar_state="expanded",
)


def apply_custom_css():
    st.markdown(
        """
    <style>
        .stApp { background: #f8fafc; color: #0f172a; }
        [data-testid="stSidebar"] { background-color: #f1f5f9; border-right: 1px solid #e2e8f0; }
        .card { background: white; border-radius: 12px; padding: 2rem; border: 1px solid #e2e8f0; box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px 0 rgba(0, 0, 0, 0.06); margin-bottom: 1.5rem; }
        .timeline-container { padding: 1rem; }
        .timeline-item { border-left: 2px solid #e2e8f0; padding-left: 1.5rem; position: relative; margin-bottom: 1.5rem; }
        .timeline-item.active { border-left-color: #2563eb; }
        .timeline-item.finished { border-left-color: #10b981; }
        .timeline-icon { position: absolute; left: -11px; top: 0; width: 20px; height: 20px; border-radius: 50%; background: white; border: 2px solid #cbd5e1; display: flex; align-items: center; justify-content: center; font-size: 0.75rem; color: #64748b; }
        .timeline-item.active .timeline-icon { border-color: #b45309; background: #fffbeb; color: #b45309; }
        .timeline-item.finished .timeline-icon { border-color: #10b981; background: #10b981; color: white; }
        .gallery-item { background: white; border-radius: 8px; padding: 1rem; text-align: center; border: 1px solid #e2e8f0; box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05); }
        .stButton > button { background-color: #ecfdf5 !important; color: #065f46 !important; border: 1px solid #a7f3d0 !important; padding: 0.75rem 1.5rem; border-radius: 6px; font-weight: 600; width: 100%; transition: all 0.2s; }
        .stButton > button:hover { transform: translateY(-1px); background-color: #d1fae5 !important; box-shadow: 0 4px 6px -1px rgba(5, 150, 105, 0.2); }
        .stTextInput > div > div > input, .stTextArea > div > div > textarea { background-color: white !important; color: #0f172a !important; border: 1px solid #cbd5e1 !important; }
    </style>
    """,
        unsafe_allow_html=True,
    )


apply_custom_css()


# Session State Initialization
def initialize_session_state():
    default_states = {
        "locked": False,
        "running": False,
        "progress": 0,
        "hide_inputs": False,
        "logs": {
            "Outline Generation": "",
            "Literature Review": "",
            "Figure Plotting": "",
            "Section Writing": "",
            "Content Refinement": "",
        },
        "current_step": 0,
        "figures": [],
        "figure_counter": 0,
        "generated_figures": [],
        "run_directory": None,
        "email_confirmed": False,
        "error_message": "",
    }
    for state_key, default_value in default_states.items():
        if state_key not in st.session_state:
            st.session_state[state_key] = default_value


initialize_session_state()


def render_sidebar():
    st.sidebar.title("🎻 Configuration")

    if st.sidebar.button("Load CVPR Example", disabled=st.session_state.locked):
        examples_directory = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "examples"
        )
        javascript_object_notation_path = os.path.join(
            examples_directory, "cvpr_example.json"
        )
        try:
            with open(javascript_object_notation_path, "r") as file_object:
                example_data = json.load(file_object)
            st.session_state.idea_text_main = example_data.get("idea", "")
            st.session_state.log_text_main = example_data.get("log", "")

            figure_path = example_data.get("figure_path")
            figure_caption = example_data.get("figure_caption", "")
            if figure_path:
                full_figure_path = os.path.join(examples_directory, figure_path)
                if os.path.exists(full_figure_path):
                    st.session_state.figures = [
                        {
                            "file": full_figure_path,
                            "name": figure_path,
                            "caption": figure_caption,
                        }
                    ]

            st.sidebar.success("🎉 Example loaded successfully!")
            time.sleep(1)
            st.rerun()
        except Exception as exception_object:
            st.sidebar.error(f"Error loading example: {exception_object}")

    models = ["gemini-3.1-pro-preview", "gemini-3-flash-preview"]
    selected_model = st.sidebar.selectbox(
        "Select Model", models, disabled=st.session_state.locked
    )

    templates = ["cvpr2025", "iclr2025"]
    selected_template = st.sidebar.selectbox(
        "Select Template", templates, disabled=st.session_state.locked
    )

    plotting_options = ["Yes", "No"]
    enable_plotting = st.sidebar.selectbox(
        "Enable Figure Generation",
        plotting_options,
        index=0,
        disabled=st.session_state.locked,
    )

    st.sidebar.markdown(
        "Your Email (for notification) <span style='color:red'>*</span>",
        unsafe_allow_html=True,
    )
    email_input = st.sidebar.text_input(
        "Email",
        key="email_input",
        label_visibility="collapsed",
        disabled=st.session_state.locked,
    )

    if st.sidebar.button("Confirm Email", disabled=st.session_state.locked):
        if st.session_state.get("email_input"):
            st.session_state.email_confirmed = True
        else:
            st.session_state.email_confirmed = False
            st.sidebar.warning("⚠️ Please enter an email address first.")

    if st.session_state.get("email_confirmed"):
        st.sidebar.success("📧 Email confirmed successfully!")

    return selected_model, selected_template, enable_plotting, email_input


selected_model, selected_template, enable_plotting, email_input = render_sidebar()

# ------------------------------------------------------------------------
# UI COMPONENT FUNCTIONS
# ------------------------------------------------------------------------


def render_gallery_tab():
    st.subheader("Uploaded Figures")
    if not st.session_state.figures:
        if not st.session_state.running:
            st.markdown(
                "<p style='color: gray; font-style: italic;'>No figures uploaded yet. Add figures from the input materials section.</p>",
                unsafe_allow_html=True,
            )
        else:
            st.info("ℹ️ No user figures provided for this run.")
    else:
        for index, figure in enumerate(st.session_state.figures):
            st.markdown(
                f'<div class="gallery-item" style="margin-bottom: 1rem;"><p style="font-weight: bold;">{figure["name"]}</p></div>',
                unsafe_allow_html=True,
            )
            st.image(figure["file"], width="stretch")
            new_caption = st.text_input(
                "Edit Caption",
                value=figure["caption"],
                key=f"edit_caption_{index}",
                disabled=st.session_state.locked,
            )
            if new_caption != figure["caption"]:
                st.session_state.figures[index]["caption"] = new_caption
            if st.button(
                "🗑️ Delete Image",
                key=f"delete_figure_{index}",
                disabled=st.session_state.locked,
            ):
                st.session_state.figures.pop(index)
                st.rerun()
            st.markdown("<hr>", unsafe_allow_html=True)

    st.subheader("Generated Figures")
    if st.session_state.get("run_directory"):
        results_path = os.path.join(
            st.session_state.run_directory, "plotting_results.json"
        )
        if os.path.exists(results_path):
            try:
                with open(results_path, "r") as file_object:
                    st.session_state.generated_figures = json.load(file_object)
            except Exception:
                pass

    if st.session_state.get("generated_figures"):
        for figure in st.session_state.generated_figures:
            image_path = os.path.join(
                st.session_state.run_directory, figure.get("image_path", "")
            )
            if os.path.exists(image_path):
                st.markdown(f"**{figure.get('title', 'Figure')}**")
                st.image(image_path, caption=figure.get("caption", ""))
                st.markdown("<hr>", unsafe_allow_html=True)


def render_json_file(file_name, title, failure_message):
    st.subheader(title)
    if st.session_state.get("run_directory"):
        file_path = os.path.join(st.session_state.run_directory, file_name)
        if os.path.exists(file_path):
            try:
                with open(file_path, "r") as file_object:
                    st.json(json.load(file_object))
            except Exception as exception_object:
                st.error(f"Error loading {title.lower()}: {exception_object}")
        elif not st.session_state.running:
            st.info(failure_message)
    else:
        st.info(failure_message)


def render_pdf_and_snapshots(pdf_path, snapshots_directory, download_key):
    if os.path.exists(pdf_path):
        with open(pdf_path, "rb") as file_object:
            st.download_button(
                label="📥 Download PDF",
                data=file_object.read(),
                file_name=os.path.basename(pdf_path),
                mime="application/pdf",
                key=download_key,
            )

        if os.path.exists(snapshots_directory):
            st.markdown("**Snapshots:**")
            image_files = sorted(
                [
                    file
                    for file in os.listdir(snapshots_directory)
                    if file.endswith(".jpg") or file.endswith(".png")
                ]
            )
            if image_files:
                grid_columns = st.columns(3)
                for index, image_file in enumerate(image_files[:3]):
                    with grid_columns[index]:
                        st.image(
                            os.path.join(snapshots_directory, image_file),
                            width="stretch",
                        )


# ------------------------------------------------------------------------
# BACKGROUND EXECUTION POLLING
# ------------------------------------------------------------------------


def handle_live_execution(
    steps, email_input, selected_template, selected_model, enable_plotting
):
    if st.session_state.running:

        if not st.session_state.get("thread_started"):
            if (
                not st.session_state.get("saved_idea")
                or not st.session_state.get("saved_log")
                or not st.session_state.get("email_input")
            ):
                st.session_state.error_message = (
                    "❌ Please fill in all required fields (Idea, Log, and Email)."
                )
                st.session_state.running = False
                st.session_state.locked = False
                st.session_state.hide_inputs = (
                    False  # Fixed: ensures inputs pop back up if validation fails
                )
                st.rerun()
            st.session_state.thread_started = True

            base_directory = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            parent_directory = os.path.dirname(base_directory)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            run_directory = os.path.join(
                parent_directory, "demo_logs", f"paper_orchestra_run_{timestamp}"
            )
            st.session_state.run_directory = run_directory
            raw_materials_directory = os.path.join(run_directory, "raw_materials")
            figures_directory = os.path.join(raw_materials_directory, "figures")

            os.makedirs(run_directory, exist_ok=True)
            os.makedirs(raw_materials_directory, exist_ok=True)
            os.makedirs(figures_directory, exist_ok=True)

            command = [
                sys.executable,
                "-u",
                os.path.join(base_directory, "paper_writing_cli.py"),
                "--raw_materials_dir",
                raw_materials_directory,
                "--output_dir",
                run_directory,
                "--latex_template_dir",
                os.path.join(base_directory, "templates", selected_template),
                "--writer_model_name",
                selected_model,
                "--reflection_model_name",
                selected_model,
                "--idea_filename",
                "idea_sparse.md",
                "--experimental_log_filename",
                "experimental_log.md",
            ]
            if enable_plotting == "Yes":
                command.extend(
                    [
                        "--use_plotting",
                        "True",
                        "--plotting_model_name",
                        selected_model,
                        "--image_model_name",
                        "gemini-3-pro-image-preview",
                    ]
                )

            def run_pipeline(
                execution_command,
                working_directory,
                steps_list,
                recipient_email,
                idea_content,
                log_content,
                figures_list,
            ):
                try:
                    libc = ctypes.CDLL(None)
                    process_set_parent_death_signal = 1

                    def set_death_signal():
                        libc.prctl(process_set_parent_death_signal, signal.SIGKILL)

                    os.makedirs(run_directory, exist_ok=True)
                    raw_materials_directory = os.path.join(
                        run_directory, "raw_materials"
                    )
                    figures_directory = os.path.join(raw_materials_directory, "figures")

                    os.makedirs(raw_materials_directory, exist_ok=True)
                    os.makedirs(figures_directory, exist_ok=True)

                    with open(
                        os.path.join(raw_materials_directory, "idea_sparse.md"), "w"
                    ) as file_object:
                        file_object.write(idea_content)

                    with open(
                        os.path.join(raw_materials_directory, "experimental_log.md"),
                        "w",
                    ) as file_object:
                        file_object.write(log_content)

                    for figure in figures_list:
                        figure_path = os.path.join(figures_directory, figure["name"])
                        if isinstance(figure["file"], str):
                            shutil.copy(figure["file"], figure_path)
                        else:
                            with open(figure_path, "wb") as file_object:
                                file_object.write(figure["file"].getvalue())

                    process = subprocess.Popen(
                        execution_command,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        cwd=working_directory,
                        preexec_fn=set_death_signal,
                    )

                    current_step_name = steps_list[0]
                    st.session_state.current_step = 0

                    while True:
                        line = process.stdout.readline()
                        if not line and process.poll() is not None:
                            break
                        if line:
                            if (
                                "Processing figure:" in line
                                or (
                                    line.strip().startswith("[")
                                    and not line.strip().startswith("[DEBUG]")
                                )
                                or "Figure processing complete" in line
                                or "Saved figures/" in line
                                or "[DEBUG] Starting run_plotting_agent" in line
                            ):
                                st.session_state.logs["Figure Plotting"] += line
                            else:
                                if "Starting Fast Hybrid Literature Agent" in line:
                                    st.session_state.current_step = 1
                                    current_step_name = steps_list[1]
                                elif "Agent SectionWritingAgent starting" in line:
                                    st.session_state.current_step = 2
                                    current_step_name = steps_list[2]
                                elif (
                                    "=== Initial Baseline Review ===" in line
                                    or "Starting dedicated formatting loop" in line
                                ):
                                    st.session_state.current_step = 3
                                    current_step_name = steps_list[3]

                                st.session_state.logs[current_step_name] += line

                    if process.poll() == 0:
                        st.session_state.current_step = len(steps_list)
                        if recipient_email:
                            attachments = []
                            run_dir = st.session_state.run_directory

                            # 1. Final PDF
                            final_pdf = os.path.join(run_dir, "final_paper.pdf")
                            if os.path.exists(final_pdf):
                                attachments.append(final_pdf)

                            # 2. LaTeX Zip
                            latex_writeup = os.path.join(run_dir, "latex_writeup")
                            final_tex = os.path.join(
                                run_dir,
                                "content_refinement_workdir",
                                "final_refined_paper.tex",
                            )

                            if os.path.exists(latex_writeup) and os.path.exists(
                                final_tex
                            ):
                                try:
                                    with tempfile.TemporaryDirectory() as tmp_dir:
                                        zip_source_dir = os.path.join(
                                            tmp_dir, "latex_source"
                                        )
                                        shutil.copytree(latex_writeup, zip_source_dir)

                                        for f_name in [
                                            "template.tex",
                                            "raw_draft_paper.tex",
                                        ]:
                                            f_path = os.path.join(
                                                zip_source_dir, f_name
                                            )
                                            if os.path.exists(f_path):
                                                os.remove(f_path)

                                        shutil.copy(
                                            final_tex,
                                            os.path.join(zip_source_dir, "main.tex"),
                                        )

                                        zip_output_base = os.path.join(
                                            run_dir, "latex_source"
                                        )
                                        shutil.make_archive(
                                            zip_output_base, "zip", zip_source_dir
                                        )

                                        if os.path.exists(zip_output_base + ".zip"):
                                            attachments.append(zip_output_base + ".zip")
                                except Exception as e:
                                    print(f" >> Error preparing latex zip: {e}")
                                    st.session_state.logs[
                                        "Content Refinement"
                                    ] += f"\n❌ Error preparing latex zip: {e}"

                            send_notification_email(
                                recipient_email,
                                "Generated Paper",
                                attachments=attachments,
                            )
                except Exception as exception_object:
                    st.session_state.logs[
                        "Content Refinement"
                    ] += f"\n❌ Error in thread: {exception_object}"
                finally:
                    st.session_state.running = False
                    st.session_state.thread_started = False

            worker_thread = threading.Thread(
                target=run_pipeline,
                args=(
                    command,
                    base_directory,
                    steps,
                    email_input,
                    st.session_state.saved_idea,
                    st.session_state.saved_log,
                    list(st.session_state.figures),
                ),
            )
            add_script_run_ctx(worker_thread)
            worker_thread.start()
            st.rerun()

        time.sleep(2)
        st.rerun()


# ------------------------------------------------------------------------
# MAIN PAGE ROUTING
# ------------------------------------------------------------------------

st.title("🎻 Paper Orchestra Demo")
st.markdown(
    "Demonstrating the automated paper writing process as detailed in [PaperOrchestra](https://arxiv.org/abs/2604.05018)."
)

steps = [
    "Outline Generation",
    "Literature Review",
    "Section Writing",
    "Content Refinement",
]

# ========================================================================
# PHASE 1: INPUT MATERIALS (Only visible when NOT running)
# ========================================================================
if not st.session_state.get("hide_inputs"):
    input_container = st.container()
    with input_container:

        if st.session_state.get("error_message"):
            st.error(st.session_state.error_message)
            st.session_state.error_message = ""

        st.header("📝 Input Materials")
        column_1, column_2 = st.columns(2)

        with column_1:
            st.subheader("💡 Research Idea")
            idea_input_type = st.radio(
                "Idea Input Type",
                ["Text", "Upload"],
                disabled=st.session_state.locked,
                key="idea_input_type_main",
            )
            if idea_input_type == "Text":
                st.markdown(
                    "Enter your idea here <span style='color:red'>*</span>",
                    unsafe_allow_html=True,
                )
                st.text_area(
                    "Idea",
                    key="idea_text_main",
                    label_visibility="collapsed",
                    disabled=st.session_state.locked,
                    height=300,
                )
            else:
                st.markdown(
                    "Upload Idea file (.md/.txt) <span style='color:red'>*</span>",
                    unsafe_allow_html=True,
                )
                uploaded_idea = st.file_uploader(
                    "Upload Idea",
                    type=["md", "txt"],
                    label_visibility="collapsed",
                    disabled=st.session_state.locked,
                    key="idea_uploader_main",
                )
                if uploaded_idea:
                    st.session_state.idea_text_main = uploaded_idea.read().decode(
                        "utf-8"
                    )

        with column_2:
            st.subheader("📊 Experimental Log")
            log_input_type = st.radio(
                "Exp Log Input Type",
                ["Text", "Upload"],
                disabled=st.session_state.locked,
                key="log_input_type_main",
            )
            if log_input_type == "Text":
                st.markdown(
                    "Enter experimental log here <span style='color:red'>*</span>",
                    unsafe_allow_html=True,
                )
                st.text_area(
                    "Exp Log",
                    key="log_text_main",
                    label_visibility="collapsed",
                    disabled=st.session_state.locked,
                    height=300,
                )
            else:
                st.markdown(
                    "Upload Exp Log file (.md/.txt) <span style='color:red'>*</span>",
                    unsafe_allow_html=True,
                )
                uploaded_log = st.file_uploader(
                    "Upload Exp Log",
                    type=["md", "txt"],
                    label_visibility="collapsed",
                    disabled=st.session_state.locked,
                    key="log_uploader_main",
                )
                if uploaded_log:
                    st.session_state.log_text_main = uploaded_log.read().decode("utf-8")

        st.subheader("🖼️ Upload Figures")
        figure_column_1, figure_column_2 = st.columns([1, 2])
        with figure_column_1:
            figure_file = st.file_uploader(
                "Upload figure",
                type=["png", "jpg", "jpeg", "pdf"],
                disabled=st.session_state.locked,
                key=f"figure_uploader_main",
            )
        with figure_column_2:
            figure_caption = st.text_input(
                "Figure Caption",
                disabled=st.session_state.locked,
                key=f"figure_caption_main",
            )

            button_column, _ = st.columns([1, 2])
            with button_column:
                st.markdown(
                    """
                <style>
                    .stButton > button { background-color: #e0e7ff !important; color: #3730a3 !important; border: 1px solid #c7d2fe !important; }
                </style>
                """,
                    unsafe_allow_html=True,
                )
                if st.button(
                    "Add Figure",
                    disabled=st.session_state.locked
                    or not figure_file
                    or not figure_caption,
                ):
                    st.session_state.figures.append(
                        {
                            "file": figure_file,
                            "name": figure_file.name,
                            "caption": figure_caption,
                        }
                    )
                    st.session_state.figure_counter += 1
                    st.success("🎉 Figure added successfully! Check the Gallery tab.")
                    time.sleep(3)
                    st.rerun()

        st.markdown(
            """
        <style>
            .stButton > button[kind="primary"] { background-color: #2563eb !important; color: white !important; font-size: 1.25rem !important; padding: 1rem 2rem !important; border: none !important; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06) !important; }
            .stButton > button[kind="primary"]:hover { background-color: #1d4ed8 !important; box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05) !important; }
        </style>
        """,
            unsafe_allow_html=True,
        )

        if st.button(
            "🚀 Begin Writing", type="primary", disabled=st.session_state.locked
        ):
            st.session_state.saved_idea = st.session_state.get("idea_text_main")
            st.session_state.saved_log = st.session_state.get("log_text_main")
            st.session_state.locked = True
            st.session_state.running = True
            st.session_state.hide_inputs = True
            st.rerun()

# ========================================================================
# PHASE 2: PROCESSING & TABS (Only visible after clicking start)
# ========================================================================
else:
    if st.session_state.get("running") or st.session_state.get("thread_started"):
        st.info(
            "🚀 Paper generation in progress! This may take 35-45 minutes. Please do not close this tab."
        )
    elif (
        not st.session_state.get("running")
        and st.session_state.get("thread_started", False) is False
    ):
        if st.session_state.get("current_step") == len(steps):
            st.success("🎉 Paper writing complete!")
        elif st.session_state.get("current_step", 0) < len(steps) and any(
            st.session_state.logs.values()
        ):
            st.error("❌ Paper writing failed or stopped unexpectedly. Check logs.")

    tabs_list = [
        "📊 Progress Timeline",
        "📥 Inputs",
        "🖼️ Figures Gallery",
        "📝 Outline",
        "🔗 Citation Map",
        "📈 Refinement Progress",
    ]
    tab_timeline, tab_inputs, tab_gallery, tab_outline, tab_citation, tab_refinement = (
        st.tabs(tabs_list)
    )

    # 1. Timeline Tab
    with tab_timeline:
        st.subheader("Writing Progress")
        for index, step in enumerate(steps):
            state_class, icon = (
                ("finished", "✓")
                if index < st.session_state.current_step
                else (
                    ("active", "⏳")
                    if index == st.session_state.current_step
                    and st.session_state.running
                    else ("", "○")
                )
            )

            if step == "Literature Review" and enable_plotting == "Yes":
                st.markdown(
                    f'<div class="timeline-item {state_class}"><div class="timeline-icon">{icon}</div><p style="font-weight: bold; margin-bottom: 0.25rem;">Literature Review</p></div>',
                    unsafe_allow_html=True,
                )
                with st.expander(
                    "View Literature Logs",
                    expanded=(index == st.session_state.current_step),
                ):
                    if st.session_state.logs["Literature Review"]:
                        st.code(st.session_state.logs["Literature Review"])
                    else:
                        st.text("No logs yet.")

                st.markdown(
                    f'<div class="timeline-item {state_class}"><div class="timeline-icon">{icon}</div><p style="font-weight: bold; margin-bottom: 0.25rem;">Figure Generation</p></div>',
                    unsafe_allow_html=True,
                )
                with st.expander(
                    "View Figure Logs",
                    expanded=(index == st.session_state.current_step),
                ):
                    if st.session_state.logs["Figure Plotting"]:
                        st.code(st.session_state.logs["Figure Plotting"])
                    else:
                        st.text("No logs yet.")
            else:
                st.markdown(
                    f'<div class="timeline-item {state_class}"><div class="timeline-icon">{icon}</div><p style="font-weight: bold; margin-bottom: 0.25rem;">{step}</p></div>',
                    unsafe_allow_html=True,
                )
                with st.expander(
                    f"View Logs for {step}",
                    expanded=(index == st.session_state.current_step),
                ):
                    if st.session_state.logs[step]:
                        st.code(st.session_state.logs[step])
                    else:
                        st.text("No logs yet.")

        if not st.session_state.running and st.session_state.get("run_directory"):
            pdf_path = os.path.join(st.session_state.run_directory, "final_paper.pdf")
            latex_directory = os.path.join(
                st.session_state.run_directory, "latex_writeup"
            )

            if os.path.exists(pdf_path) or os.path.exists(latex_directory):
                st.markdown("### 📥 Download Results")
                column_download_1, column_download_2 = st.columns(2)

                if os.path.exists(pdf_path):
                    with open(pdf_path, "rb") as file_object:
                        with column_download_1:
                            st.download_button(
                                label="📄 Download Final PDF",
                                data=file_object.read(),
                                file_name="final_paper.pdf",
                                mime="application/pdf",
                                key="download_final_pdf_tab",
                            )

                if os.path.exists(latex_directory):
                    zip_buffer = io.BytesIO()
                    with zipfile.ZipFile(
                        zip_buffer, "a", zipfile.ZIP_DEFLATED, False
                    ) as zip_file:
                        for root, directories, files in os.walk(latex_directory):
                            for file in files:
                                file_path = os.path.join(root, file)
                                archive_name = os.path.relpath(
                                    file_path, latex_directory
                                )
                                zip_file.write(file_path, archive_name)

                    with column_download_2:
                        st.download_button(
                            label="📦 Download LaTeX Source",
                            data=zip_buffer.getvalue(),
                            file_name="latex_source.zip",
                            mime="application/zip",
                            key="download_final_latex_tab",
                        )

    # 2. Inputs Tab
    with tab_inputs:
        st.header("📥 User Inputs")
        st.markdown(
            "<h3 style='background-color: #ffe6e6; padding: 5px; border-radius: 3px;'>Idea</h3>",
            unsafe_allow_html=True,
        )
        st.markdown(
            st.session_state.get(
                "saved_idea", "*(No input provided or process not started)*"
            )
        )
        st.markdown(
            "<h3 style='background-color: #ffffcc; padding: 5px; border-radius: 3px;'>Experimental Log</h3>",
            unsafe_allow_html=True,
        )
        st.markdown(
            st.session_state.get(
                "saved_log", "*(No input provided or process not started)*"
            )
        )

    # 3. Gallery Tab
    with tab_gallery:
        render_gallery_tab()

    # 4. Outline Tab
    with tab_outline:
        render_json_file("outline.json", "Paper Outline", "No outline generated yet.")

    # 5. Citation Map Tab
    with tab_citation:
        render_json_file(
            os.path.join("literature_agent_output", "citation_map.json"),
            "Citation Map",
            "No citation map generated yet.",
        )

    # 6. Refinement Tab
    with tab_refinement:
        st.header("Content & Format Refinement Progress")
        if not st.session_state.get("run_directory"):
            st.info("No refinement progress available yet.")
        else:
            worklog_path = os.path.join(
                st.session_state.run_directory,
                "content_refinement_workdir",
                "content_refinement_worklog.json",
            )

            st.markdown("### Content Refinement")
            columns = st.columns(2)

            initial_pdf_path = os.path.join(
                st.session_state.run_directory,
                "content_refinement_workdir",
                "initial_draft.pdf",
            )
            if os.path.exists(initial_pdf_path):
                with columns[0]:
                    with st.expander("Content Refinement V0 (Initial)"):
                        st.write("Initial draft compiled.")
                        render_pdf_and_snapshots(
                            initial_pdf_path,
                            os.path.join(
                                st.session_state.run_directory,
                                "content_refinement_workdir",
                                "pdf_screenshots",
                                "content_refinement",
                                "v0",
                            ),
                            "download_content_0",
                        )

            if os.path.exists(worklog_path):
                try:
                    with open(worklog_path, "r") as file_object:
                        worklog_data = json.load(file_object)

                    content_versions = list(worklog_data.keys())

                    for index, version_key in enumerate(content_versions):
                        entry = worklog_data[version_key]
                        with columns[(index + 1) % 2]:
                            with st.expander(
                                f"Content Refinement {version_key.upper()}"
                            ):
                                st.write(f"**Outcome:** {entry.get('outcome')}")
                                st.write(f"**Total Gain:** {entry.get('total_gain')}")
                                st.write(f"**Total Drop:** {entry.get('total_drop')}")

                                if "scores_before" in entry and "scores_after" in entry:
                                    st.markdown("**Scores:**")
                                    for axis in [
                                        "Overall",
                                        "Originality",
                                        "Quality",
                                        "Clarity",
                                    ]:
                                        st.write(
                                            f"- {axis}: {entry['scores_before'].get(axis, 0)} -> {entry['scores_after'].get(axis, 0)}"
                                        )

                                render_pdf_and_snapshots(
                                    os.path.join(
                                        st.session_state.run_directory,
                                        "content_refinement_workdir",
                                        f"refined_paper_{version_key}.pdf",
                                    ),
                                    os.path.join(
                                        st.session_state.run_directory,
                                        "content_refinement_workdir",
                                        "pdf_screenshots",
                                        "content_refinement",
                                        version_key,
                                    ),
                                    f"download_content_{version_key}",
                                )

                    final_selected_version = next(
                        (
                            f"V{entry['round']}"
                            for entry in worklog_data.values()
                            if entry.get("outcome")
                            in [
                                "ACCEPTED_SCORE_INCREASE",
                                "ACCEPTED_NEUTRAL_IMPROVEMENT",
                            ]
                        ),
                        "V0 (Initial)",
                    )

                    format_worklog_path = os.path.join(
                        st.session_state.run_directory,
                        "content_refinement_workdir",
                        "format_refinement_worklog.json",
                    )
                    if os.path.exists(format_worklog_path):
                        st.info(
                            f"💡 `Content Refinement {final_selected_version}` is selected at the output of the content refinement phase, now move on to formatting refinement..."
                        )

                        st.markdown("### Format Refinement")

                        format_iterations = []
                        with open(format_worklog_path, "r") as file_object:
                            for version_key, entry in json.load(file_object).items():
                                format_iterations.append(
                                    {
                                        "iteration": int(version_key[1:]),
                                        "feedback": entry.get(
                                            "formatting_feedback", {}
                                        ),
                                        "pdf_path": os.path.join(
                                            st.session_state.run_directory,
                                            "content_refinement_workdir",
                                            f"formatted_candidate_{version_key}.pdf",
                                        ),
                                        "screenshots_directory": os.path.join(
                                            st.session_state.run_directory,
                                            "content_refinement_workdir",
                                            "pdf_screenshots",
                                            "format_refinement",
                                            version_key,
                                        ),
                                    }
                                )

                        format_columns = st.columns(2)

                        with format_columns[0]:
                            with st.expander("Format Refinement V0 (Initial)"):
                                st.write("Input from content refinement phase.")
                                source_pdf_name = (
                                    "initial_draft.pdf"
                                    if final_selected_version == "V0 (Initial)"
                                    else f"refined_paper_v{final_selected_version[1:]}.pdf"
                                )
                                pdf_path = os.path.join(
                                    st.session_state.run_directory,
                                    "content_refinement_workdir",
                                    source_pdf_name,
                                )

                                if os.path.exists(pdf_path):
                                    with open(pdf_path, "rb") as file_object:
                                        st.download_button(
                                            label="📥 Download PDF",
                                            data=file_object.read(),
                                            file_name=source_pdf_name,
                                            mime="application/pdf",
                                            key="download_format_0",
                                        )

                        for index, entry in enumerate(format_iterations):
                            with format_columns[(index + 1) % 2]:
                                with st.expander(
                                    f"Format Refinement V{entry['iteration']}"
                                ):
                                    if "figure_and_tables" in entry["feedback"]:
                                        st.markdown("**Figure & Table Issues:**")
                                        st.json(entry["feedback"]["figure_and_tables"])
                                    render_pdf_and_snapshots(
                                        entry["pdf_path"],
                                        entry["screenshots_directory"],
                                        f"download_format_{entry['iteration']}",
                                    )

                        if os.path.exists(
                            os.path.join(
                                st.session_state.run_directory,
                                "content_refinement_workdir",
                                "final_refined_paper.pdf",
                            )
                        ):
                            if format_iterations:
                                max_iter = max(
                                    entry["iteration"] for entry in format_iterations
                                )
                                st.info(
                                    f"💡 `Format Refinement V{max_iter}` is selected as the final output of this pipeline."
                                )
                            else:
                                st.info(
                                    "💡 `final_refined_paper.pdf` is selected as the final output of this pipeline."
                                )
                        else:
                            st.info(
                                "💡 Refinement pipeline ended without producing a final separated PDF."
                            )

                except Exception as exception_object:
                    st.error(f"Error processing refinement data: {exception_object}")
            elif not st.session_state.running and not os.path.exists(initial_pdf_path):
                st.info("No refinement progress available yet.")

    handle_live_execution(
        steps, email_input, selected_template, selected_model, enable_plotting
    )
