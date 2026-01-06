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
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;700;800&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Outfit', sans-serif;
    }

    .stApp { 
        background-color: #0B0E14; 
    }
    
    /* Header Container */
    .header-container {
        display: flex;
        flex-direction: column;
        align-items: center;
        padding: 2rem 0;
        margin-bottom: 1rem;
    }
    
    .title-row {
        display: flex;
        align-items: center;
        gap: 20px;
        margin-bottom: 5px;
    }
    
    .shield-icon {
        font-size: 3.5rem;
        color: #00ADB5;
        text-shadow: 0 0 20px rgba(0, 173, 181, 0.5);
    }
    
    .main-header {
        font-size: 3.8rem; 
        font-weight: 800;
        color: #00ADB5;
        text-shadow: 0 0 15px rgba(0, 173, 181, 0.3);
        margin: 0;
        letter-spacing: -1px;
    }
    
    .sub-header {
        font-size: 0.9rem;
        font-weight: 500;
        color: #888;
        letter-spacing: 2px;
        text-transform: uppercase;
        margin-top: 10px;
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 12px;
    }

    /* Metric Cards */
    .metric-row {
        display: flex;
        justify-content: space-between;
        gap: 20px;
        margin-bottom: 30px;
    }
    
    .metric-card {
        background: #161B22;
        border: 1px solid #30363D;
        border-radius: 12px;
        padding: 20px;
        flex: 1;
        text-align: center;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
        transition: transform 0.2s ease;
    }
    
    .metric-card:hover {
        transform: translateY(-5px);
        border-color: #00ADB5;
    }
    
    .metric-label {
        font-size: 0.85rem;
        color: #8B949E;
        margin-bottom: 10px;
        font-weight: 600;
    }
    
    .metric-value {
        font-size: 1.8rem;
        font-weight: 700;
        color: #FFFFFF;
        margin: 0;
    }

    .status-normal {
        color: #00FF9D;
        text-shadow: 0 0 15px rgba(0, 255, 157, 0.4);
    }
    
    .status-critical {
        color: #FF2E63;
        text-shadow: 0 0 15px rgba(255, 46, 99, 0.4);
    }
    
    .score-value {
        color: #00ADB5;
    }
    
    .alert-value {
        color: #F9AD6A;
    }

    .live-badge {
        display: inline-block; width: 10px; height: 10px;
        background-color: #FF0000; border-radius: 50%;
        box-shadow: 0 0 8px #FF0000;
        animation: blinker 1.5s linear infinite;
    }
    @keyframes blinker { 50% { opacity: 0; } }

    /* Section divider */
    .section-title {
        font-size: 1.5rem;
        font-weight: 700;
        color: #FFFFFF;
        margin: 40px 0 10px 0;
        display: flex;
        align-items: center;
        gap: 10px;
    }
    .section-subtitle {
        font-size: 0.85rem;
        color: #00ADB5;
        font-weight: 600;
        margin-bottom: 20px;
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
@st.cache_resource
def get_kafka_consumer():
    kafka_config = get_kafka_config()
    consumer = KafkaConsumer(
        kafka_config.get_topic('sensor_data'),
        bootstrap_servers=kafka_config.get_bootstrap_servers(),
        value_deserializer=lambda x: json.loads(x.decode('utf-8')),
        auto_offset_reset='latest',
        enable_auto_commit=True,
        consumer_timeout_ms=100  # Non-blocking
    )
    return consumer

kafka_consumer = get_kafka_consumer()

# --- SIDEBAR UI ---
with st.sidebar:
    st.title("🛡️ Ensemble Control")
    
    # --- SIMULATION CONTROLS ---
    st.header("Data Stream Source")
    # Get current global state
    from utils import get_system_state
    global_state = get_system_state()
    
    # Data Mode Control as Selectbox
    source_map = {"Normal Data": "Normal", "Attack Data": "Attack"}
    inv_source_map = {v: k for k, v in source_map.items()}
    current_mode = global_state.get("data_mode", "Normal")
    
    stream_source = st.selectbox("Select One", ["Normal Data", "Attack Data"], 
                               index=0 if current_mode == "Normal" else 1)
    new_mode = source_map[stream_source]

    st.divider()

    # --- DETECTION CONTROLS ---
    st.header("Detection Sensitivity")
    # Multiplier slider for live threshold adjustment
    threshold_mult = st.slider("DL Threshold Mult", 0.5, 5.0, 1.0, 0.1)
    
    # Calculate live threshold based on multiplier
    adj_threshold = detector.ae_threshold * threshold_mult
    st.info(f"🚀 Active Threshold: {adj_threshold:.2f}")

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
    st.header("�📧 Email Status")
    
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
st.markdown(f"""
    <div class="header-container">
        <div class="title-row">
            <div class="shield-icon">🛡️</div>
            <h1 class="main-header">SWaT AI Guardian</h1>
        </div>
        <div class="sub-header">
            <span class="live-badge"></span> 
            LIVE SYSTEM MONITORING | CRITICAL INFRASTRUCTURE PROTECTION
        </div>
    </div>
""", unsafe_allow_html=True)

# Metrics Grid using styled HTML because st.metric is hard to style as requested
m1, m2, m3, m4 = st.columns(4)
metric_counts = m1.empty()
metric_status = m2.empty()
metric_mse = m3.empty()
metric_alerts = m4.empty()

st.markdown('<div class="section-title">🧠 Real-time Anomaly Detection</div>', unsafe_allow_html=True)
st.markdown('<div class="section-subtitle">🤖 AI Anomaly Detection Engine</div>', unsafe_allow_html=True)

# Charts Section
c1, c2 = st.columns([2, 1])
with c1:
    chart_mse_ph = st.empty()
with c2:
    telemetry_ph = st.empty()

# --- STATE MANAGEMENT ---
if "history" not in st.session_state:
    st.session_state.history = {
        "time": deque(maxlen=100),
        "mse": deque(maxlen=100),
        "threshold": deque(maxlen=100),
        "is_dl": deque(maxlen=100),
        "is_iso": deque(maxlen=100),
        "sensors": deque(maxlen=100)
    }
    st.session_state.alerts = []
    st.session_state.event_log = deque(maxlen=100) # Keep last 100 events
    st.session_state.total = 0
    st.session_state.notifier = NotificationManager()

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

# We keep processing until the loop time expires, then rerun to check UI inputs
while run_sim and (time.time() - start_loop_time < LOOP_TIME_SECONDS):
    # Consume messages from Kafka
    messages = kafka_consumer.poll(timeout_ms=100, max_records=1)
    
    if not messages:
        time.sleep(0.1)
        continue

    for topic_partition, records in messages.items():
        for record in records:
            raw_data = record.value
            st.session_state.total += 1
            
            # Preprocess and Predict
            features = detector.preprocess(raw_data)
            res = detector.predict(features, adj_threshold)
            
            mse = res["mse"]
            dl_ano = res["is_anomaly"]
            iso_ano = res["is_iso"]
            current_mse = mse
            timestamp = time.strftime("%H:%M:%S")
            label = raw_data.get("Normal/Attack", "Unknown")
            
            status_type = "NORMAL"
            is_anomaly = (dl_ano or iso_ano)
            
            if is_anomaly:
                # 1. Determine Alarm Type
                alarm_category = "AI ANOMALY" # Default
                
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
                    # Proxy for Hard-wired/Critical severity (High MSE)
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
                
                # --- CONTINUOUS ALARM LOGIC ---
                # Only render if not already active to prevent stuttering loops
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
                        window.sirenInterval = setInterval(playSiren, 1000);
                    })();
                    </script>
                    """
                    with audio_ph:
                        st.components.v1.html(siren_html, height=0, width=0)
                    local_alarm_active = True

                # Email Logic with cooldown
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
                # Normal State -> Stop Alarm
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
            
            st.session_state.history["sensors"].append({
                "Time": timestamp,
                "Flow": raw_data.get("FIT101", 0),
                "Level": raw_data.get("LIT101", 0),
                "Pressure": raw_data.get("P102", 0)
            })

    # --- UPDATE UI PLACEHOLDERS ---
    with metric_counts:
        st.markdown(f'<div class="metric-card"><div class="metric-label">Events</div><div class="metric-value">{st.session_state.total}</div></div>', unsafe_allow_html=True)
    
    with metric_status:
        is_anomaly = st.session_state.history["is_dl"][-1] or st.session_state.history["is_iso"][-1] if st.session_state.history["is_dl"] else False
        s_class = "status-critical" if is_anomaly else "status-normal"
        s_text = "CRITICAL" if is_anomaly else "NORMAL"
        st.markdown(f'<div class="metric-card"><div class="metric-label">Status</div><div class="metric-value {s_class}">{s_text}</div></div>', unsafe_allow_html=True)
        
    with metric_mse:
        current_mse = st.session_state.history["mse"][-1] if st.session_state.history["mse"] else 0
        score_display = f"{current_mse:.6f}"
        st.markdown(f'<div class="metric-card"><div class="metric-label">Score</div><div class="metric-value score-value">{score_display}</div></div>', unsafe_allow_html=True)
        
    with metric_alerts:
        st.markdown(f'<div class="metric-card"><div class="metric-label">Alerts</div><div class="metric-value alert-value">{len(st.session_state.alerts)}</div></div>', unsafe_allow_html=True)

    if st.session_state.history["mse"]:
        h_df = pd.DataFrame({
            "Time": list(st.session_state.history["time"]), 
            "MSE": [float(x) for x in st.session_state.history["mse"]],
        }).reset_index(names='Recent Events')
        
        y_max = max(h_df["MSE"].max(), adj_threshold)
        y_limit = float(y_max * 1.2)
        
        area = alt.Chart(h_df).mark_area(
            line={'color': '#00ADB5', 'strokeWidth': 2},
            color=alt.Gradient(gradient='linear', stops=[alt.GradientStop(color='#00ADB5', offset=0), alt.GradientStop(color='rgba(0, 173, 181, 0)', offset=1)])
        ).encode(
            x=alt.X('Recent Events:Q', title='Recent Events', axis=alt.Axis(labels=False)),
            y=alt.Y('MSE:Q', title='Anomaly Score', scale=alt.Scale(domain=[0, y_limit], clamp=True)),
            tooltip=['MSE']
        ).properties(height=300)

        threshold_line = alt.Chart(pd.DataFrame({'y': [adj_threshold]})).mark_rule(
            color='#FF2E63', strokeDash=[5, 5], size=2
        ).encode(y='y:Q')

        chart_mse_ph.altair_chart(alt.layer(area, threshold_line), use_container_width=True)
        log_ph.table(pd.DataFrame(st.session_state.event_log).head(10))

    if st.session_state.history["sensors"]:
        t_df = pd.DataFrame(list(st.session_state.history["sensors"]))
        t_df_melted = t_df.melt('Time', var_name='Sensor', value_name='Value')
        c_telemetry = alt.Chart(t_df_melted).mark_line().encode(
            x='Time:O', y='Value:Q', color=alt.Color('Sensor:N', scale=alt.Scale(range=['#00ADB5', '#F9AD6A', '#FF2E63']))
        ).properties(height=250, title="Live Sensor Telemetry")
        telemetry_ph.altair_chart(c_telemetry, use_container_width=True)

    time.sleep(0.02)

# After loop or if simulation stopped, trigger a rerun to handle widget updates
if run_sim:
    st.rerun()
else:
    time.sleep(1.0)
    st.rerun()
