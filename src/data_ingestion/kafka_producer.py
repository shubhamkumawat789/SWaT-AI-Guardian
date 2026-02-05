import pandas as pd
import json
import time
from kafka import KafkaProducer
import os
import sys

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils import get_kafka_config, get_system_state

def start_producer():
    config = get_kafka_config()
    topic = config.get_topic("sensor_data")
    bootstrap = config.get_bootstrap_servers()

    print(f"[*] Starting Producer on {topic} at {bootstrap}...")
    
    try:
        producer = KafkaProducer(
            bootstrap_servers=bootstrap,
            value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )
    except Exception as e:
        print(f"[!] FAILED: {e}")
        return

    # Cache for files
    files = {
        "Normal": "data/proceed/normal.csv",
        "Attack": "data/proceed/attack.csv"
    }
    
    data_cache = {}
    for mode, path in files.items():
        if os.path.exists(path):
            print(f"[*] Loading {mode} data into cache...")
            df = pd.read_csv(path)
            df.columns = df.columns.str.strip()
            
            # --- SMART FILTERING ---
            # Ensure we strip whitespace from VALUES in the label column to catch "Normal " vs "Normal"
            if "Normal/Attack" in df.columns:
                df["Normal/Attack"] = df["Normal/Attack"].astype(str).str.strip()

            # Ensure "Attack" mode only plays ACTUAL attacks
            if mode == "Attack" and "Normal/Attack" in df.columns:
                print(f"    Filtering Attack file... Original: {len(df)}")
                # Keep only rows where label is NOT Normal
                df = df[df["Normal/Attack"] != "Normal"].reset_index(drop=True)
                print(f"    Active Attacks Only: {len(df)} rows")
            
            # Ensure "Normal" mode is pure
            if mode == "Normal" and "Normal/Attack" in df.columns:
                 df = df[df["Normal/Attack"] == "Normal"].reset_index(drop=True)
                 print(f"    Normal Data Cleaned: {len(df)} rows")

            data_cache[mode] = df
        else:
            print(f"[!] Warning: {mode} data file not found at {path}")

    if not data_cache:
        print("[!] FATAL: No data files found.")
        return

    print("[*] Streaming started (Dynamic Control enabled)...")
    
    indices = { "Normal": 0, "Attack": 0 }
    
    while True:
        state = get_system_state()
        
        if not state["run_system"]:
            time.sleep(1.0)
            continue
            
        mode = state.get("data_mode", "Normal")
        if mode not in data_cache or data_cache[mode].empty:
            # Fallback
            mode = "Normal" if "Normal" in data_cache else list(data_cache.keys())[0]
            
        df = data_cache[mode]
        idx = indices[mode]
        
        if idx >= len(df):
            idx = 0 # Loop the data
            
        row = df.iloc[idx]
        record = row.to_dict()
        record['record_id'] = int(idx)
        record['timestamp'] = time.time()
        record['data_mode'] = mode
        
        producer.send(topic, record)
        indices[mode] = idx + 1
        
        if idx % 100 == 0:
            producer.flush()
            print(f"    Mode: {mode} | Streamed {idx} records...")
        
        # Calculate delay from speed (e.g., speed=1.0 -> 0.01s delay, speed=0.1 -> 0.1s delay)
        speed = state.get("simulation_speed", 1.0)
        delay = 0.01 / max(speed, 0.001)
        time.sleep(delay)

if __name__ == "__main__":
    start_producer()
