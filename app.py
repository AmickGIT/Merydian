import streamlit as st
import json
import sys
from pathlib import Path
import time
from datetime import datetime
import pandas as pd
import logging

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from agents.agent_controller import AgentController
from ortools.sat.python import cp_model

st.set_page_config(page_title="Merydian Engine Demo", page_icon="🤖", layout="wide")

if "app_logs" not in st.session_state:
    st.session_state.app_logs = []
if "cpsat_logs" not in st.session_state:
    st.session_state.cpsat_logs = []

from streamlit.runtime.scriptrunner import get_script_run_ctx, add_script_run_ctx
import threading

# Monkey-patch OR-Tools CpSolver to capture C++ logs
original_init = cp_model.CpSolver.__init__

def custom_init(self, *args, **kwargs):
    original_init(self, *args, **kwargs)
    ctx = get_script_run_ctx()
    
    def log_callback(message):
        if ctx:
            add_script_run_ctx(threading.current_thread(), ctx)
        if "cpsat_logs" in st.session_state:
            st.session_state.cpsat_logs.append(message)
            # Update the UI every 15 lines to prevent Streamlit from hanging
            if len(st.session_state.cpsat_logs) % 15 == 0 and "cpsat_placeholder" in st.session_state:
                st.session_state.cpsat_placeholder.code("\n".join(st.session_state.cpsat_logs), language="log")
                
    self.log_callback = log_callback

cp_model.CpSolver.__init__ = custom_init

class StreamlitLogHandler(logging.Handler):
    def __init__(self, placeholder):
        super().__init__()
        self.placeholder = placeholder
        self.logs = st.session_state.app_logs

    def emit(self, record):
        log_entry = self.format(record)
        self.logs.append(log_entry)
        self.placeholder.code("\n".join(self.logs), language="log")

st.title("Merydian Engine Demo - Live Feedback Agent")
st.markdown("This demo interacts directly with the backend engine (`agents` and `ml_or`). You can provide custom customer feedback and see how the engine processes it, triggers the optimizer, and generates explanations.")

@st.cache_resource
def get_controller():
    return AgentController()

controller = get_controller()

# Define Paths
data_dir = project_root / "ml_or" / "data"
initial_solution_path = data_dir / "initial_optimized_solution.json"
base_prefs_path = data_dir / "family_preferences_3fam_strict.json"

if not initial_solution_path.exists():
    st.error(f"Initial baseline solution not found at {initial_solution_path}!")
    st.info("Run `python -m agents.optimizer_agent` first to generate it.")
    st.stop()

def parse_itinerary_to_df(solution_path):
    with open(solution_path, 'r') as f:
        data = json.load(f)
    
    total_families = len(data.get("families", []))
    parsed_data = []
    
    for day_data in data.get("days", []):
        day = day_data.get("day")
        activity_map = {}
        
        for fam_id, fam_data in day_data.get("families", {}).items():
            for poi in fam_data.get("pois", []):
                arr = poi.get("arrival_time")
                dep = poi.get("departure_time")
                loc = poi.get("location_name")
                key = (arr, dep, loc)
                
                if key not in activity_map:
                    activity_map[key] = []
                activity_map[key].append(fam_id)
        
        for (arr, dep, loc), fams in activity_map.items():
            fams.sort()
            status = "Together" if len(fams) == total_families else "Split"
            parsed_data.append({
                "Day": day,
                "Time": f"{arr} - {dep}",
                "Activity": loc,
                "Families": ", ".join(fams),
                "Status": status
            })
            
    df = pd.DataFrame(parsed_data)
    if not df.empty:
        df = df.sort_values(by=["Day", "Time"]).reset_index(drop=True)
    return df

def highlight_status(val):
    if val == "Split":
        return 'color: #ff4b4b; font-weight: bold;'
    elif val == "Together":
        return 'color: #21c354; font-weight: bold;'
    return ''

# Session State Initialization
if "scenarios_run" not in st.session_state:
    st.session_state.scenarios_run = []
if "current_solution" not in st.session_state:
    st.session_state.current_solution = initial_solution_path
if "current_prefs" not in st.session_state:
    st.session_state.current_prefs = base_prefs_path

# Layout definition
col_main, col_log = st.columns([2, 1])

with col_log:
    st.subheader("Terminal Logs (Live)")
    # Native scrolling container for logs
    log_container = st.container(height=400)
    log_placeholder = log_container.empty()
    if st.session_state.app_logs:
        log_placeholder.code("\n".join(st.session_state.app_logs), language="log")
        
    st.subheader("Optimizer Logs (CP-SAT)")
    cpsat_container = st.container(height=400)
    st.session_state.cpsat_placeholder = cpsat_container.empty()
    if st.session_state.cpsat_logs:
        st.session_state.cpsat_placeholder.code("\n".join(st.session_state.cpsat_logs), language="log")

with col_main:
    st.header("Current Itinerary in Focus")
    current_df = parse_itinerary_to_df(st.session_state.current_solution)
    if not current_df.empty:
        st.dataframe(
            current_df.style.map(highlight_status, subset=['Status']),
            hide_index=True
        )
    else:
        st.warning("No itinerary data found.")
    
    st.markdown("---")
    st.subheader("Add Custom Customer Feedback")
    
    with open(st.session_state.current_solution, 'r') as f:
        baseline = json.load(f)
    families = baseline.get('families', [])
    num_days = len(baseline.get('days', []))
    
    with st.form("feedback_form"):
        f_col1, f_col2 = st.columns([1, 1])
        with f_col1:
            family_id = st.selectbox("Family ID", families + ["Global/Other"])
        with f_col2:
            current_day = st.number_input("Current Day (0-indexed)", min_value=0, max_value=max(0, num_days-1), value=0)
        
        user_input = st.text_area("Customer Feedback Input", "We absolutely must visit Qutub Minar tomorrow on Day 2, it's a must-see for us.")
        submit_button = st.form_submit_button("Submit Feedback")

    if submit_button and user_input:
        context = {"current_day": current_day}
        if family_id != "Global/Other":
            context["family_id"] = family_id
        
        context["previous_solution"] = str(st.session_state.current_solution)
        if st.session_state.current_prefs:
            context["current_preferences_path"] = str(st.session_state.current_prefs)
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = project_root / "agents" / "tests" / f"demo_run_streamlit_{timestamp}"
        output_dir.mkdir(parents=True, exist_ok=True)
        context["output_dir"] = str(output_dir)
        
        try:
            st.info("🧠 Engine is processing your feedback...")
            
            # Setup logging for this run
            st.session_state.app_logs.append(f"\n[{datetime.now().strftime('%H:%M:%S')}] NEW SCENARIO ------------------------")
            st.session_state.cpsat_logs.append(f"\n[{datetime.now().strftime('%H:%M:%S')}] NEW OPTIMIZATION JOB ------------------------")
            
            handler = StreamlitLogHandler(log_placeholder)
            handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - \n%(message)s\n'))
            
            agents_logger = logging.getLogger('agents')
            agents_logger.setLevel(logging.INFO)
            agents_logger.addHandler(handler)
            
            httpx_logger = logging.getLogger('httpx')
            httpx_logger.addHandler(handler)
            
            try:
                result = controller.process_user_input(user_input, context)
            finally:
                agents_logger.removeHandler(handler)
                httpx_logger.removeHandler(handler)
                # Ensure the final batch of cpsat logs are printed
                if "cpsat_placeholder" in st.session_state and st.session_state.cpsat_logs:
                    st.session_state.cpsat_placeholder.code("\n".join(st.session_state.cpsat_logs), language="log")
            
            explanations = []
            optimizer_output_dir = None
            
            if result['optimizer_output']:
                optimizer_output_dir = Path(result['optimizer_output']['llm_payloads']).parent
                payloads_file = optimizer_output_dir / "llm_payloads.json"
                
                if payloads_file.exists():
                    with open(payloads_file, 'r', encoding='utf-8') as f:
                        payload_data = json.load(f)
                    
                    payloads_to_process = []
                    if isinstance(payload_data, dict):
                        if "families" in payload_data:
                            payloads_to_process.extend(payload_data["families"])
                        if "travel_agent" in payload_data:
                            payloads_to_process.append(payload_data["travel_agent"])
                    elif isinstance(payload_data, list):
                        payloads_to_process = payload_data
                    
                    if payloads_to_process:
                        st.success("✅ Optimizer Triggered! Generating personalized explanations (streaming live)...")
                        for payload in payloads_to_process:
                            name = payload.get("family_id") or payload.get("audience", "Unknown")
                            with st.expander(f"Explanation for {name}", expanded=True):
                                with st.spinner(f"Groq is generating explanation for {name}..."):
                                    explanation = controller.explainability_agent.explain(payload)
                                    st.write(explanation.summary)
                                    explanations.append({
                                        "audience": payload.get("audience", "FAMILY"),
                                        "family_id": name,
                                        "explanation": explanation.summary
                                    })
                                    time.sleep(2)
                
                optimized_solution_file = optimizer_output_dir / "optimized_solution.json"
                if optimized_solution_file.exists():
                    st.session_state.current_solution = optimized_solution_file
                
                updated_prefs_file = optimizer_output_dir / "family_preferences_updated.json"
                if updated_prefs_file.exists():
                    st.session_state.current_prefs = updated_prefs_file
            else:
                st.warning("⚠️ Engine decided NOT to run the Optimizer for this feedback.")
    
            scenario_output = {
                "input": user_input,
                "event": result['event'].model_dump(),
                "decision": result['decision'].model_dump(),
                "optimizer_triggered": result['decision'].action == "RUN_OPTIMIZER",
                "explanations": explanations
            }
            st.session_state.scenarios_run.append(scenario_output)
            
            st.success("Scenario Complete! Click below to view the updated itinerary.")
            if st.button("Refresh View"):
                st.rerun()
                
        except Exception as e:
            st.error(f"Error processing feedback: {e}")

    # Display past scenarios
    if st.session_state.scenarios_run:
        st.markdown("---")
        st.subheader("Run History")
        for i, run in enumerate(reversed(st.session_state.scenarios_run)):
            with st.expander(f"Run {len(st.session_state.scenarios_run) - i}: {run['input'][:50]}...", expanded=False):
                st.write("**Input:**", run["input"])
                st.write("**Event Type:**", run["event"]["event_type"])
                st.write("**Decision Action:**", run["decision"]["action"])
                
                if run["optimizer_triggered"]:
                    st.write("✅ Optimizer Triggered")
                    for exp in run["explanations"]:
                        st.info(f"**{exp['family_id']}**: {exp['explanation']}")
                else:
                    st.write("❌ Optimizer Not Triggered")
