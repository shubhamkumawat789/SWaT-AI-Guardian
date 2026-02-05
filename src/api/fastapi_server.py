from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Optional
import time
import json
import os
from kafka import KafkaConsumer
from threading import Thread
import sys

# Add src to path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

app = FastAPI(title="SWaT AI API", version="1.0.0")

# In-memory storage for latest alerts (managed in a background thread or via Redis in production)
LATEST_ALERTS = []
MAX_ALERTS = 100

class Alert(BaseModel):
    timestamp: float
    severity: str
    mse: float
    threshold: float
    record_id: str

@app.get("/")
async def root():
    return {
        "status": "online",
        "system": "Secure Water Treatment Anomaly Detection",
        "timestamp": time.time()
    }

@app.get("/alerts", response_model=List[Dict])
async def get_alerts():
    """Fetch latest 100 alerts"""
    return LATEST_ALERTS

def kafka_listener():
    """Background thread to mirror Kafka alerts into memory for the API"""
    retries = 0
    max_retries = 10
    
    while retries < max_retries:
        try:
            from utils import get_kafka_config
            config = get_kafka_config()
            topic = config.get_topic("alerts")
            bootstrap = config.get_bootstrap_servers()
            
            consumer = KafkaConsumer(
                topic,
                bootstrap_servers=bootstrap,
                value_deserializer=lambda v: json.loads(v.decode("utf-8")),
                auto_offset_reset="latest"
            )
            
            print(f"[*] API Kafka Listener started on {topic}")
            for message in consumer:
                alert = message.value
                LATEST_ALERTS.insert(0, alert)
                if len(LATEST_ALERTS) > MAX_ALERTS:
                    LATEST_ALERTS.pop()
            break # Exit loop if connection successful and loop completes (unlikely for consumer)
        except Exception as e:
            print(f"[!] API Kafka Listener failed (Attempt {retries+1}/{max_retries}): {e}")
            retries += 1
            time.sleep(2 ** retries) # Exponential backoff

# Start Kafka listener thread
thread = Thread(target=kafka_listener, daemon=True)
thread.start()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
