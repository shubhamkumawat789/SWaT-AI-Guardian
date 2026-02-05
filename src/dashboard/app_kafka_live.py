import os
import sys
# Priority Path: Ensure the local src/ is first
BASE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if BASE_PATH not in sys.path:
    sys.path.insert(0, BASE_PATH)

import utils
import importlib
importlib.reload(utils) 

import streamlit as st
import pandas as pd
import numpy as np
import time
import datetime
import altair as alt
from kafka import KafkaConsumer
import json
import threading
from collections import deque

from inference.streaming_inference import AnomalyDetector
from notifications import NotificationManager
from utils import get_kafka_config, setup_structured_logging, set_system_status, get_system_status

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="SWaT AI Guardian",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CSS STYLING ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap');
    
    /* Global Reset & Font */
    html, body, [class*="css"] {
        font-family: 'Outfit', sans-serif;
        background-color: #050505; 
        color: #E0E0E0;
    }
    
    .stApp {
        background-image: radial-gradient(circle at 50% -20%, #1e293b 0%, #050505 60%);
        background-attachment: fixed;
    }
    
    /* Fix for header being hidden - Aggressive Override */
    div[data-testid="block-container"] {
        padding-top: 5rem !important;
        padding-bottom: 5rem !important;
    }

    /* --- GLASSMORPHISM CARDS --- */
    .glass-card {
        background: rgba(30, 41, 59, 0.4);
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 16px;
        padding: 24px;
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.3);
        transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
    }

    .glass-card:hover {
        transform: translateY(-4px);
        border-color: rgba(0, 242, 195, 0.3);
        box-shadow: 0 12px 40px 0 rgba(0, 242, 195, 0.1);
    }
    
    /* --- HEADER STYLES --- */
    .main-title {
        font-size: 3.5rem;
        font-weight: 700;
        color: #FFFFFF;
        text-shadow: 0 0 20px rgba(0, 242, 195, 0.6);
        letter-spacing: -1.5px;
        margin-bottom: 0.5rem;
    }
    
    .subtitle-badge {
        background: rgba(0, 242, 195, 0.1);
        color: #00F2C3;
        padding: 6px 16px;
        border-radius: 20px;
        font-size: 0.85rem;
        font-weight: 600;
        letter-spacing: 1px;
        border: 1px solid rgba(0, 242, 195, 0.2);
        display: inline-flex;
        align-items: center;
        gap: 8px;
    }

    /* --- METRIC TYPOGRAPHY --- */
    .metric-label {
        font-size: 0.9rem;
        color: #94A3B8;
        margin-bottom: 8px;
        font-weight: 500;
        text-transform: uppercase;
        letter-spacing: 1.5px;
    }
    
    .metric-value {
        font-size: 2.2rem;
        font-weight: 700;
        color: #FFFFFF;
        font-variant-numeric: tabular-nums;
    }
    
    /* Status Colors */
    .status-good { color: #00F2C3; text-shadow: 0 0 15px rgba(0, 242, 195, 0.4); }
    .status-warn { color: #FFB86C; text-shadow: 0 0 15px rgba(255, 184, 108, 0.4); }
    .status-crit { color: #FF5555; text-shadow: 0 0 15px rgba(255, 85, 85, 0.4); }
    
    /* --- ANIMATIONS --- */
    @keyframes pulse-red {
        0% { box-shadow: 0 0 0 0 rgba(255, 85, 85, 0.4); }
        70% { box-shadow: 0 0 0 10px rgba(255, 85, 85, 0); }
        100% { box-shadow: 0 0 0 0 rgba(255, 85, 85, 0); }
    }
    
    @keyframes pulse-green {
        0% { box-shadow: 0 0 0 0 rgba(0, 242, 195, 0.4); }
        70% { box-shadow: 0 0 0 10px rgba(0, 242, 195, 0); }
        100% { box-shadow: 0 0 0 0 rgba(0, 242, 195, 0); }
    }

    .live-dot {
        width: 12px;
        height: 12px;
        border-radius: 50%;
        background: #00F2C3;
        box-shadow: 0 0 10px #00F2C3;
        animation: pulse-green 2s infinite;
    }
    
    .live-dot.critical {
        background: #FF5555;
        box-shadow: 0 0 10px #FF5555;
        animation: pulse-red 1s infinite;
    }

    /* --- CHART CONTAINERS --- */
    .chart-container {
        background: rgba(15, 23, 42, 0.6);
        border: 1px solid rgba(255, 255, 255, 0.05);
        border-radius: 12px;
        padding: 20px;
    }
</style>
""", unsafe_allow_html=True)

# Paths for Cache Invalidation
MODELS_DIR = os.path.abspath(os.path.join(BASE_PATH, "..", "models"))
CHECK_FILE = os.path.join(MODELS_DIR, "threshold.json")

# --- INITIALIZATION ---
@st.cache_resource
def load_engine(mtime_key):
    # Model loading only once - persistent in memory until files change on disk
    return AnomalyDetector(init_kafka=False)  # Don't init Kafka in detector

# Detect if model was recently retrained to force reload
current_mtime = os.path.getmtime(CHECK_FILE) if os.path.exists(CHECK_FILE) else 0
detector = load_engine(current_mtime)

# --- KAFKA CONSUMER SETUP ---
# --- CONSUMER SETUP (KAFKA OR SIMULATOR) ---
class FileSimulatedConsumer:
    """
    Simulates a Kafka Consumer by reading from a CSV file.
    Used for 'Resume/Demo Mode' when no real Kafka broker is available (e.g. Streamlit Cloud).
    """
    def __init__(self, file_path):
        self.file_path = file_path
        self._generator = self._record_generator()
        print(f"⚠️ KAFKA NOT FOUND: Switching to Simulation Mode using {file_path}")

    def _record_generator(self):
        """Yields records from the CSV file infinitely (loops)."""
        while True:
            try:
                # Read CSV in chunks to avoid memory issues
                for chunk in pd.read_csv(self.file_path, chunksize=1000):
                    # Convert dataframe rows to dicts
                    records = chunk.to_dict('records')
                    for record in records:
                        # Add metadata expected by the dashboard
                        if "Normal/Attack" in record:
                            record["Normal/Attack"] = record["Normal/Attack"]
                        else:
                            record["Normal/Attack"] = "Unknown"
                        
                        # Simulate Kafka Message structure
                        yield MockMessage(record)
            except FileNotFoundError:
                st.error(f"❌ Simulation Data not found: {self.file_path}")
                time.sleep(10)
            except Exception as e:
                print(f"Simulation Error: {e}")
                time.sleep(1)

    def poll(self, timeout_ms=0, max_records=500):
        """Mimics kafka_consumer.poll()"""
        # Slow down simulation to mimic real-time
        # time.sleep(0.01) 
        
        batch = {}
        records = []
        # Fetch a small batch
        for _ in range(max_records):
            records.append(next(self._generator))
            
        # Structure: {Partition: [Records]}
        batch["partition_0"] = records
        return batch

class MockMessage:
    def __init__(self, value):
        self.value = value

# --- SIDEBAR UI ---
with st.sidebar:
    st.title("🛡️ Ensemble Control")
    status_placeholder = st.empty()
    status_placeholder.markdown("⚪ **System Status:** Connecting...")
    
     # --- SIMULATION CONTROLS ---
    st.header("Data Stream Source")
    # Get current global state
    from utils import get_system_state
    global_state = get_system_state()
    
    # Data Mode Control as Selectbox
    source_map = {"Normal Data": "Normal", "Attack Data": "Attack"}
    inv_source_map = {v: k for k, v in source_map.items()}
    
    # Force Start on "Normal" for new sessions (Recruiter Friendly)
    if "session_mode_init" not in st.session_state:
        current_mode = "Normal"
        st.session_state.session_mode_init = True
        set_system_status(mode="Normal") # Reset persistent file
    else:
        current_mode = global_state.get("data_mode", "Normal")
    
    stream_source = st.selectbox("Select One", ["Normal Data", "Attack Data"], 
                               index=0 if current_mode == "Normal" else 1)
    new_mode = source_map[stream_source]
    
    @st.cache_resource(hash_funcs={FileSimulatedConsumer: lambda _: None})
    def init_consumer(mode_lbl):
        """
        Initialize Consumer based on mode.
        If Kafka fails, load the specific CSV for that mode.
        """
        # 1. Try Real Kafka First
        try:
            kafka_config = get_kafka_config()
            consumer = KafkaConsumer(
                kafka_config.get_topic('sensor_data'),
                bootstrap_servers=kafka_config.get_bootstrap_servers(),
                value_deserializer=lambda x: json.loads(x.decode('utf-8')),
                auto_offset_reset='latest',
                enable_auto_commit=True,
                consumer_timeout_ms=100
            )
            # Check connectivity
            consumer.topics()
            
            # --- CRITICAL FIX: SKIP backlog to Instant Real-Time ---
            # When Dashboard connects, ignore old buffered messages
            try:
                consumer.poll(timeout_ms=100) # Dummy poll to assign partitions
                parts = consumer.assignment()
                if parts:
                    consumer.seek_to_end(*parts) # Jump to end
            except Exception:
                pass 
                
            return consumer, "KAFKA"
        except Exception:
            pass # Fallback
            
        # 2. Simulation Fallback
        if mode_lbl == "Normal":
            # Cloud Deployment Optimization: Prefer sample if full file missing
            full_path = os.path.join(BASE_PATH, "..", "data", "normal.csv")
            if os.path.exists(full_path):
                file_name = "normal.csv"
            else:
                file_name = "normal_sample.csv"
        else:
            file_name = "attack.csv"
        
        # Try finding it relative to BASE_PATH
        data_path = os.path.join(BASE_PATH, "..", "data", file_name)
        if not os.path.exists(data_path):
             # Try absolute lookup from current file
            data_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", file_name))
            
        if os.path.exists(data_path):
            return FileSimulatedConsumer(data_path), "SIMULATION"
        else:
             # Fallback to attack.csv if current file missing
            fallback_path = os.path.join(BASE_PATH, "..", "data", "attack.csv")
            if os.path.exists(fallback_path):
                 return FileSimulatedConsumer(fallback_path), "SIMULATION"
            
            st.error(f"❌ Data not found: {file_name}")
            st.stop()

    # Init Consumer Dynamic Loading
    consumer_instance, sys_mode = init_consumer(new_mode)
    
    if sys_mode == "KAFKA":
        status_placeholder.markdown("🟢 **System Status:** Online (Kafka)")
    else:
        status_placeholder.markdown("🟢 **System Status:** Online (Archived Stream)")
        if new_mode == "Normal":
            st.caption("✅ System Validating Normal Operations based on Physics")
        else:
            st.caption("🚨 Simulating Cyber-Attack Traffic")


    st.divider()

    # --- DETECTION CONTROLS ---
    st.header("Detection Sensitivity")
    # Multiplier slider for live threshold adjustment
    # Default set to 1.3 to avoid False Positives during "Normal" demo phase
    threshold_mult = st.slider("DL Threshold Mult", 0.5, 5.0, 1.3, 0.1)
    
    # Calculate live threshold based on multiplier
    adj_threshold = detector.ae_threshold * threshold_mult
    st.info(f"🌱 Natural Threshold: {adj_threshold:.4f}")

    st.divider()

    # Speed Control
    st.header("Simulation Settings")
    sim_speed = st.slider("Streaming Speed", 0.01, 10.0, float(global_state["simulation_speed"]), 0.01)
    
    # RUN / STOP
    run_sim = st.toggle("🚀 RUN SYSTEM", value=global_state["run_system"])
    
    # Sync with global state
    set_system_status(run=run_sim, speed=sim_speed, mode=new_mode)

    if st.button("Reset Dashboard"):
        if hasattr(detector, 'raw_data_buffer'):
            detector.raw_data_buffer.clear()
        st.session_state.clear()
        st.rerun()
    


    st.divider()
    st.header("📧 Email Status")
    
    # 1. Ensure Notifier exists in session state
    if 'notifier' not in st.session_state:
        st.session_state.notifier = NotificationManager()

    notifier = st.session_state.notifier

    # 2. Status & Test Email Logic
    if notifier.sender_email and notifier.sender_password:
        st.success(f"✅ Connected: {notifier.sender_email}")
        
        if st.button("Send Test Email"):
            current_score = 0.0
            if "history" in st.session_state and st.session_state.history["mse"]:
                current_score = st.session_state.history["mse"][-1]
            
            test_alert = {
                "Time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "Type": "MANUAL_DASHBOARD_TEST",
                "Score": f"{current_score:.4f}",
                "Threshold": f"{adj_threshold:.2f}",
                "Status": "🚨 ATTACK DETECTED" if current_score > adj_threshold else "✅ SYSTEM NORMAL"
            }
            
            with st.spinner("Sending live alert..."):
                if notifier.send_email(test_alert, ignore_cooldown=True):
                    st.toast(f"Email Sent! Score: {current_score:.2f}")
                else:
                    st.error("Failed. Check App Password or Internet.")
    else:
        st.markdown('<div style="background-color:rgba(255,165,0,0.1); padding:10px; border-radius:5px; border:1px solid orange; color:orange; font-size:0.8rem; text-align:center;">Setup Incomplete</div>', unsafe_allow_html=True)

    st.divider()
    st.header("📊 Kafka Status")
    st.info("🔴 LIVE: Monitoring Stream")


# --- MAIN UI ---
# Horizontal Header Layout properly spaced from top
st.markdown(f"""
    <div style="
        display: flex; 
        align-items: center; 
        justify-content: center; 
        gap: 20px; 
        margin-top: 60px; 
        margin-bottom: 40px;
    ">
        <div style="font-size: 4rem; filter: drop-shadow(0 0 10px rgba(0, 242, 195, 0.3));">🛡️</div>
        <div style="text-align: left;">
            <h1 class="main-title" style="margin-bottom: 5px; font-size: 3.5rem;">SWaT AI GUARDIAN</h1>
            <div class="subtitle-badge">
                 <div class="live-dot"></div>
                 REAL-TIME PROTECTION &bull; PRODUCTION READY
            </div>
        </div>
    </div>
""", unsafe_allow_html=True)

# Metrics Grid using styled HTML because st.metric is hard to style as requested
m1, m2, m3, m4 = st.columns(4)
metric_counts = m1.empty()
metric_status = m2.empty()
metric_mse = m3.empty()
metric_alerts = m4.empty()

st.markdown('<div class="section-title">🤖 Real-Time AI Anomaly Detection Engine</div>', unsafe_allow_html=True)

# Charts Section
c1, c2 = st.columns([2, 1])
with c1:
    chart_mse_ph = st.empty()
with c2:
    telemetry_ph = st.empty()

# Attribution Placeholder (Full Warning Width)
st.markdown("---")
attr_ph = st.empty()

# --- STATE MANAGEMENT ---
if "history" not in st.session_state:
    # Pre-fill with zeros to ensure graph is visible immediately (No Layout Shift)
    init_len = 50
    now = time.time()
    
    # Generate initial timestamps
    init_times = [time.strftime("%H:%M:%S", time.localtime(now - i)) for i in range(init_len, 0, -1)]
    
    # Get default threshold if available, else 0.01
    default_thresh = detector.ae_threshold if hasattr(detector, 'ae_threshold') else 0.01
    
    st.session_state.history = {
        "time": deque(init_times, maxlen=100),
        "mse": deque([0.001] * init_len, maxlen=100), 
        "threshold": deque([default_thresh] * init_len, maxlen=100),
        "is_dl": deque([False] * init_len, maxlen=100),
        "is_iso": deque([False] * init_len, maxlen=100),
        "sensors": deque([{ 
            "Time": t, 
            "Flow": 0.0, 
            "Level": 0.0, 
            "Pressure": 0.0 
        } for t in init_times], maxlen=100)
    }
    st.session_state.alerts = []
    st.session_state.event_log = deque(maxlen=100) # Keep last 100 events
    st.session_state.total = 0
    st.session_state.notifier = NotificationManager()
    st.session_state.attribution = {}

# --- LOGS AREA ---
st.markdown("### 🚨 Security Event Log")
log_ph = st.empty()
# Limit event log size to 100 for safety (redundant due to maxlen but good practice)
if len(st.session_state.event_log) > 100:
    st.session_state.event_log = deque(list(st.session_state.event_log)[:100], maxlen=100)

# --- REFRESH RATE CONTROL ---
# We use a limited loop to provide "Natural Motion" without full reloads
LOOP_TIME_SECONDS = 3.0
start_loop_time = time.time()

# Audio Placeholder for Continuous Alarm
audio_ph = st.empty()
local_alarm_active = False

def update_dashboard_view():
    """Renders all dashboard elements based on current session state."""
    with metric_counts:
        st.markdown(f'<div class="glass-card"><div class="metric-label">Events Scanned</div><div class="metric-value">{st.session_state.total}</div></div>', unsafe_allow_html=True)
    
    with metric_status:
        # Determine Status
        is_anomaly = False
        if st.session_state.history["is_dl"]:
            is_anomaly = st.session_state.history["is_dl"][-1] or st.session_state.history["is_iso"][-1]

        s_class = "status-crit" if is_anomaly else "status-good"
        s_text = "THREAT DETECTED" if is_anomaly else "SECURE"
        dot_class = "critical" if is_anomaly else ""
        
        st.markdown(f'''
        <div class="glass-card">
            <div class="metric-label">System Status</div>
            <div style="display:flex;align-items:center;gap:15px">
                <div class="live-dot {dot_class}"></div>
                <div class="metric-value {s_class}" style="font-size:1.6rem">{s_text}</div>
            </div>
        </div>
        ''', unsafe_allow_html=True)
        
    with metric_mse:
        current_mse = st.session_state.history["mse"][-1] if st.session_state.history["mse"] else 0.0
        score_display = f"{current_mse:.5f}"
        st.markdown(f'<div class="glass-card"><div class="metric-label">Anomaly Score</div><div class="metric-value">{score_display}</div></div>', unsafe_allow_html=True)
        
    with metric_alerts:
        n_alerts = len(st.session_state.alerts)
        color = "status-warn" if n_alerts > 0 else ""
        st.markdown(f'<div class="glass-card"><div class="metric-label">Total Alerts</div><div class="metric-value {color}">{n_alerts}</div></div>', unsafe_allow_html=True)

    if st.session_state.history["mse"]:
        h_df = pd.DataFrame({
            "Time": list(st.session_state.history["time"]), 
            "MSE": [float(x) for x in st.session_state.history["mse"]],
            "Threshold_Line": [adj_threshold] * len(st.session_state.history["mse"])
        }).reset_index(names='Recent_Events')
        
        y_max = max(h_df["MSE"].max(), adj_threshold)
        y_limit = max(float(y_max * 1.2), 1.0)
        
        # Base Chart
        base = alt.Chart(h_df).encode(
            x=alt.X('Recent_Events:Q', title='Recent Events', axis=alt.Axis(labels=False))
        )

        # 1. Area Chart for MSE
        area = base.mark_area(
            line={'color': '#00ADB5', 'strokeWidth': 2},
            color=alt.Gradient(gradient='linear', stops=[
                alt.GradientStop(color='#00ADB5', offset=0), 
                alt.GradientStop(color='rgba(0, 173, 181, 0)', offset=1)
            ])
        ).encode(
            y=alt.Y('MSE:Q', title='Anomaly Score', scale=alt.Scale(domain=[0, y_limit], clamp=True)),
            tooltip=['Time', 'MSE']
        )

        # 2. Threshold Line
        threshold_rule = base.mark_rule(
            color='#FF2E63', strokeDash=[5, 5], size=2
        ).encode(
            y='Threshold_Line:Q'
        )

        chart_mse_ph.altair_chart((area + threshold_rule), use_container_width=True)
        
        # Update Event Log
        log_ph.table(pd.DataFrame(st.session_state.event_log).head(10))

    if st.session_state.history["sensors"]:
        t_df = pd.DataFrame(list(st.session_state.history["sensors"]))
        t_df_melted = t_df.melt('Time', var_name='Sensor', value_name='Value')
        c_telemetry = alt.Chart(t_df_melted).mark_line().encode(
            x='Time:O', y='Value:Q', color=alt.Color('Sensor:N', scale=alt.Scale(range=['#00ADB5', '#F9AD6A', '#FF2E63']))
        ).properties(height=250, title="Live Sensor Telemetry")
        telemetry_ph.altair_chart(c_telemetry, use_container_width=True)

    if "attribution" in st.session_state and st.session_state.attribution:
        attr_data = pd.DataFrame(
            list(st.session_state.attribution.items()),
            columns=['Sensor', 'Deviation']
        ).sort_values(by='Deviation', ascending=False)
        
        c_attr = alt.Chart(attr_data).mark_bar().encode(
            x=alt.X('Deviation:Q', title='Anomaly Contribution (Scaled Deviation)'),
            y=alt.Y('Sensor:N', sort='-x', title=None),
            color=alt.Color('Deviation:Q', scale=alt.Scale(scheme='orangered')),
            tooltip=['Sensor', 'Deviation']
        ).properties(height=250, title="⚡ Root Cause Analysis (Top contributors)")
        
        attr_ph.altair_chart(c_attr, use_container_width=True)
    else:
        attr_ph.empty()

# We keep processing until the loop time expires, then rerun to check UI inputs
while run_sim and (time.time() - start_loop_time < LOOP_TIME_SECONDS):
    # Consume messages from Kafka or Simulator
    messages = consumer_instance.poll(timeout_ms=100, max_records=50)
    
    if not messages:
        # Even if empty, render current state to maintain smoothness
        update_dashboard_view()
        time.sleep(0.1)
        continue

    for topic_partition, records in messages.items():
        for record in records:
            raw_data = record.value
            
            # --- LAG FILTER (INSTANT SWITCH) ---
            # Check the actual label in the data vs what the user selected
            current_label = raw_data.get("Normal/Attack", "Unknown")
            
            # If user wants Normal, but data is Attack -> SKIP
            if new_mode == "Normal" and (current_label == "Attack" or "Attack" in current_label):
                continue
                
            # If user wants Attack, but data is Normal -> SKIP
            if new_mode == "Attack" and (current_label == "Normal" or "Normal" in current_label):
                continue
                
            st.session_state.total += 1
            
            # Preprocess and Predict
            features = detector.preprocess(raw_data)
            res = detector.predict(features, adj_threshold)
            
            mse = res["mse"]
            dl_ano = res["is_anomaly"]
            iso_ano = res["is_iso"]
            timestamp = time.strftime("%H:%M:%S")
            label = raw_data.get("Normal/Attack", "Unknown")
            
            status_type = "NORMAL"
            is_anomaly = (dl_ano or iso_ano)
            
            if is_anomaly:
                # 1. Determine Alarm Type
                alarm_category = "AI ANOMALY"
                
                # Check Persistence (if previous sample was also anomalous)
                is_persistent = False
                if len(st.session_state.history["is_dl"]) > 0:
                    if st.session_state.history["is_dl"][-1] or st.session_state.history["is_iso"][-1]:
                        is_persistent = True

                # Classification Logic
                if is_persistent:
                    alarm_category = "PERSISTENCE ALARM"
                    status_type = "PERSISTENT TE"
                elif mse > (adj_threshold * 3):
                    alarm_category = "CRITICAL THRESHOLD" 
                    status_type = "CRITICAL"
                else:
                    alarm_category = "RECONSTRUCTION ALARM"
                    status_type = "WARNING"

                alert_entry = {
                    "Time": timestamp,
                    "Type": alarm_category, 
                    "Score": f"{mse:.6f}",
                    "Label": label
                }
                st.session_state.alerts.insert(0, alert_entry) 
                
                # --- SOUND LOGIC RESTORED ---
                if not local_alarm_active:
                    siren_html = """
                    <script>
                    (function() {
                        var AudioContext = window.AudioContext || window.webkitAudioContext;
                        if (!window.sirenCtx) {
                            window.sirenCtx = new AudioContext();
                        }
                        var ctx = window.sirenCtx;
                        
                        if (ctx.state === 'suspended') {
                            ctx.resume();
                        }

                        function playSiren() {
                            var osc = ctx.createOscillator();
                            var gain = ctx.createGain();
                            
                            osc.connect(gain);
                            gain.connect(ctx.destination);
                            
                            // Industrial Buzzer: Square Wave for harsh alert
                            osc.type = 'square'; 
                            osc.frequency.setValueAtTime(150, ctx.currentTime);
                            
                            gain.gain.setValueAtTime(0.15, ctx.currentTime);
                            gain.gain.linearRampToValueAtTime(0.15, ctx.currentTime + 0.8);
                            gain.gain.linearRampToValueAtTime(0, ctx.currentTime + 0.9);
                            
                            osc.start(ctx.currentTime);
                            osc.stop(ctx.currentTime + 0.9);
                        }
                        
                        // Loop the buzzer every 1.0 second
                        playSiren();
                        if (window.sirenInterval) clearInterval(window.sirenInterval);
                        window.sirenInterval = setInterval(playSiren, 1000);
                    })();
                    </script>
                    """
                    with audio_ph:
                        st.components.v1.html(siren_html, height=0, width=0)
                    local_alarm_active = True

                # Email Logic
                now = datetime.datetime.now()
                last_sent = st.session_state.notifier.last_sent_time
                if last_sent is None or (now - last_sent).total_seconds() > 300:
                    st.session_state.notifier.last_sent_time = now
                    threading.Thread(
                        target=st.session_state.notifier.send_email, 
                        args=(alert_entry, True), 
                        daemon=True
                    ).start()
            
            else:
                if local_alarm_active:
                    audio_ph.empty()
                    local_alarm_active = False

            st.session_state.event_log.appendleft({
                "Time": timestamp,
                "Type": status_type,
                "Score": f"{mse:.6f}",
                "Limit": f"{adj_threshold:.5f}",
                "Label": label
            })
            
            st.session_state.history["time"].append(timestamp)
            st.session_state.history["mse"].append(mse)
            st.session_state.history["threshold"].append(adj_threshold)
            st.session_state.history["is_dl"].append(dl_ano)
            st.session_state.history["is_iso"].append(iso_ano)
            
            if "top_features" in res:
                st.session_state.attribution = res["top_features"]
            else:
                st.session_state.attribution = {}

            st.session_state.history["sensors"].append({
                "Time": timestamp,
                "Flow": raw_data.get("FIT101", 0),
                "Level": raw_data.get("LIT101", 0),
                "Pressure": raw_data.get("P102", 0)
            })

    # Optimization: Reduce refresh rate to 0.5s to stop chart flickering ("jap jap")
    if time.time() - start_loop_time > 0.5:
        update_dashboard_view()
        # Reset relative to loop start isn't needed as we just want to update periodically within the 3s window
    
    time.sleep(0.5)

# Ensure view is updated even if simulation is stopped (Static View)
if not run_sim:
    update_dashboard_view()

# After loop or if simulation stopped, trigger a rerun to handle widget updates
if run_sim:
    st.rerun()
else:
    time.sleep(1.0)
    st.rerun()
