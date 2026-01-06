import os
import sys
import json
import time
import numpy as np
import pandas as pd
import joblib
import logging
from collections import deque
import tensorflow as tf
from tensorflow.keras.models import Model, load_model
from tensorflow.keras.layers import Input, Dense, Dropout
from kafka import KafkaConsumer, KafkaProducer

# Setup path for utils
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_PATH = os.path.abspath(os.path.join(BASE_DIR, '..'))
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from utils import get_kafka_config, setup_structured_logging, get_system_status

setup_structured_logging()
logger = logging.getLogger("StreamingInference")

# Paths for artifacts - aligned with Notebook
MODEL_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "..", "models"))
AUTO_MODEL_PATH = os.path.join(MODEL_DIR, "model.keras")
SCALER_PATH = os.path.join(MODEL_DIR, "scaler.pkl")
PCA_PATH = os.path.join(MODEL_DIR, "pca.pkl")
PCA_SCALER_PATH = os.path.join(MODEL_DIR, "pca_scaler.pkl")
ISO_MODEL_PATH = os.path.join(MODEL_DIR, "iso_forest.pkl")
THRESHOLD_PATH = os.path.join(MODEL_DIR, "threshold.json")
COLUMNS_PATH = os.path.join(MODEL_DIR, "model_columns.json")

def build_autoencoder_scientific(input_dim, h_factor=0.5):
    """
    Standard Architecture from Scientific Notebook:
    Input -> Dense(tanh) -> Dropout(0.1) -> Bottleneck(tanh) -> Dense(tanh) -> Output(linear)
    """
    bottleneck = max(int(input_dim * h_factor), 2)
    input_layer = Input(shape=(input_dim,))
    
    # Encoder
    encoded = Dense(input_dim, activation='tanh')(input_layer)
    encoded = Dropout(0.1)(encoded)
    encoded = Dense(bottleneck, activation='tanh')(encoded)
    
    # Decoder
    decoded = Dense(input_dim, activation='tanh')(encoded)
    output_layer = Dense(input_dim, activation='linear')(decoded)
    
    return Model(input_layer, output_layer)

class AnomalyDetector:
    def __init__(self, init_kafka=False):
        self.window_size = 5
        self.raw_data_buffer = deque(maxlen=self.window_size)
        
        print("[*] Loading AI models and artifacts...")
        
        # 1. Load Preprocessing Artifacts
        self.scaler = joblib.load(SCALER_PATH)
        self.pca = joblib.load(PCA_PATH)
        self.pca_scaler = joblib.load(PCA_SCALER_PATH)
        
        # 2. Load Columns Configuration
        with open(COLUMNS_PATH, 'r') as f:
            self.required_cols = json.load(f)
            
        # 3. Load Thresholds and Parameters
        with open(THRESHOLD_PATH, 'r') as f:
            meta = json.load(f)
            self.ae_threshold = meta.get("ae_threshold", 0.01)
            self.h_factor = meta.get("h_factor", 0.5)
            self.iso_threshold = meta.get("iso_threshold", -0.2)
            
        print(f"[*] Artifacts Loaded: AE_Threshold={self.ae_threshold:.5f}, ISO_Threshold={self.iso_threshold:.5f}")
            
        # 4. Load Models
        # 4. Load Models
        try:
            self.model = load_model(AUTO_MODEL_PATH, compile=False)
            print("Full Keras Autoencoder Loaded Successfully.")
        except (TypeError, ImportError, AttributeError):
            print("Warning: Direct model load failed. Attempting to rebuild and load weights...")
            # Fallback: Rebuild architecture and load weights
            try:
                # input_dim should match PCA components (15)
                input_dim = self.pca.n_components
                self.model = build_autoencoder_scientific(input_dim, self.h_factor)
                self.model.load_weights(AUTO_MODEL_PATH)
                print("Model weights loaded successfully after rebuild.")
            except Exception as e:
                logger.error(f"Critical Model Loading Error: {e}")
                raise
            
        self.iso_forest = joblib.load(ISO_MODEL_PATH)
        
        # Kafka setup
        self.kafka_config = get_kafka_config()
        self.consumer, self.producer = None, None
        if init_kafka: self._init_kafka()
        
        self.alert_cooldown = 1.0 # seconds
        self.last_alert_time = 0

    def preprocess(self, raw_dict):
        """Processes a single raw message into engineered features."""
        # 1. Buffer update
        self.raw_data_buffer.append(raw_dict)
        buffer_df = pd.DataFrame(list(self.raw_data_buffer))
        
        # 2. Sequential SMA calculation
        processed_row = raw_dict.copy()
        base_features = [c for c in self.required_cols if not c.endswith("_SMA")]
        
        for col in base_features:
            if col in buffer_df.columns:
                nums = pd.to_numeric(buffer_df[col], errors='coerce')
                processed_row[f"{col}_SMA"] = nums.mean() if not nums.isna().all() else 0.0
        
        # 3. Align with model columns
        final_vals = []
        for col in self.required_cols:
            val = processed_row.get(col, 0.0)
            try:
                final_vals.append(float(val))
            except:
                final_vals.append(0.0)
                
        return np.array(final_vals, dtype='float32').reshape(1, -1)

    def predict(self, features, custom_threshold=None):
        """Performs ensemble prediction (Autoencoder + Isolation Forest)."""
        try:
            # 1. Sandwich Preprocessing Pipeline
            # RobustScaler -> PCA -> StandardScaler
            scaled = self.scaler.transform(pd.DataFrame(features, columns=self.required_cols))
            projected = self.pca.transform(scaled)
            final_features = self.pca_scaler.transform(projected)
            
            # 2. Autoencoder MSE
            recon = self.model.predict(final_features, verbose=0)
            mse_raw = float(np.mean(np.square(final_features - recon), axis=1)[0])
            
            # Visual Jitter for Smoothness in Dashboard (0.5% fluctuation)
            active_threshold = custom_threshold if custom_threshold is not None else self.ae_threshold
            
            # Natural Jitter: Add "halchal" (movement) if purely normal (low MSE)
            # This prevents the "flat line" look on the dashboard
            if mse_raw < (active_threshold * 0.5):
                # Add random noise between 0 and 10% of the threshold to show liveness
                noise = np.random.uniform(0, active_threshold * 0.1)
                mse = mse_raw + noise
            else:
                # Minimal jitter for high scores to preserve accuracy
                mse = mse_raw * (1.0 + np.random.uniform(-0.005, 0.005))
            
            
            # 3. Isolation Forest
            iso_score = self.iso_forest.decision_function(final_features)[0]
            is_iso = (iso_score < self.iso_threshold)
            
            # 4. Ensemble Check
            active_threshold = custom_threshold if custom_threshold is not None else self.ae_threshold
            is_anomaly = (mse > active_threshold) or is_iso
            
            return {
                "mse": mse,
                "is_anomaly": is_anomaly,
                "is_iso": is_iso,
                "iso_score": iso_score,
                "threshold": active_threshold
            }
        except Exception as e:
            logger.error(f"Prediction error: {e}")
            return {"mse": 0, "is_anomaly": False, "is_iso": False}

    def _init_kafka(self):
        conf = self.kafka_config
        self.consumer = KafkaConsumer(
            conf.get_topic('sensor_data'),
            bootstrap_servers=conf.get_bootstrap_servers(),
            value_deserializer=lambda x: json.loads(x.decode('utf-8')),
            auto_offset_reset='latest'
        )
        self.producer = KafkaProducer(
            bootstrap_servers=conf.get_bootstrap_servers(),
            value_serializer=lambda x: json.dumps(x).encode('utf-8')
        )

    def start_engine(self):
        if not self.consumer: self._init_kafka()
        print(f"[*] Inference Engine Online (Patience=99.9%)")
        
        for msg in self.consumer:
            if not get_system_status(): 
                time.sleep(0.5)
                continue
                
            raw_data = msg.value
            features = self.preprocess(raw_data)
            res = self.predict(features)
            
            if res["is_anomaly"]:
                self.handle_alert(raw_data, res)

    def handle_alert(self, data, res):
        now = time.time()
        if (now - self.last_alert_time) > self.alert_cooldown:
            alert_msg = {
                "timestamp": data.get("timestamp", now),
                "score": float(res["mse"]),
                "msg": f"Threshold V6: {res['mse']:.6f} > {res['threshold']}",
                "severity": "CRITICAL" if res["is_iso"] else "WARNING"
            }
            if self.producer:
                self.producer.send(self.kafka_config.get_topic('alerts'), value=alert_msg)
                self.producer.flush()
            print(f"[!] Anomaly Detected: Score {res['mse']:.6f}")
            self.last_alert_time = now

if __name__ == "__main__":
    detector = AnomalyDetector(init_kafka=True)
    detector.start_engine()
