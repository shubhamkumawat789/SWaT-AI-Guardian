import os
import sys
import datetime
import json
import pandas as pd
import numpy as np
import joblib

# Explicit import to prevent DLL load failed errors on some Windows/WSL setups
try:
    import scipy.linalg
except ImportError:
    pass

from sklearn.preprocessing import RobustScaler, StandardScaler
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest
import tensorflow as tf
from tensorflow.keras.models import Model
from tensorflow.keras.layers import Input, Dense, Dropout
from tensorflow.keras.callbacks import EarlyStopping

# Setup paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, "..", ".."))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
MODEL_DIR = os.path.join(PROJECT_ROOT, "models")
PROCEED_DIR = os.path.join(DATA_DIR, "proceed")

if not os.path.exists(MODEL_DIR):
    os.makedirs(MODEL_DIR)

# Artifact Paths
MODEL_PATH = os.path.join(MODEL_DIR, "model.h5")
WEIGHTS_PATH = os.path.join(MODEL_DIR, "model_weights.h5")
ISO_FOREST_PATH = os.path.join(MODEL_DIR, "iso_forest.pkl")
THRESHOLD_PATH = os.path.join(MODEL_DIR, "threshold.json")
SCALER_PATH = os.path.join(MODEL_DIR, "scaler.pkl")
PCA_PATH = os.path.join(MODEL_DIR, "pca.pkl")
PCA_SCALER_PATH = os.path.join(MODEL_DIR, "pca_scaler.pkl")
COLUMNS_PATH = os.path.join(MODEL_DIR, "model_columns.json")

def build_autoencoder_scientific(input_dim, h_factor=0.5):
    """
    Standard Architecture from Scientific Notebook:
    Input -> Dense(tanh) -> Dropout(0.1) -> Bottleneck(tanh) -> Dense(tanh) -> Output(linear)
    """
    bottleneck = max(int(input_dim * h_factor), 2)
    input_layer = Input(shape=(input_dim,), name='ae_input')
    
    # Encoder
    encoded = Dense(input_dim, activation='tanh', name='encoder_dense_1')(input_layer)
    encoded = Dropout(0.1, name='encoder_dropout')(encoded)
    encoded = Dense(bottleneck, activation='tanh', name='bottleneck')(encoded)
    
    # Decoder
    decoded = Dense(input_dim, activation='tanh', name='decoder_dense_1')(encoded)
    output_layer = Dense(input_dim, activation='linear', name='ae_output')(decoded)
    
    return Model(input_layer, output_layer, name='autoencoder')

def main():
    print("[*] Starting Production Training Pipeline...", flush=True)

    # 1. Load Data
    print("Loading data...", flush=True)
    normal_csv = os.path.join(PROCEED_DIR, "normal.csv")
    if not os.path.exists(normal_csv):
        print(f"[!] Critical: {normal_csv} not found.")
        return

    # Load only necessary amount if file is huge, but for production we usually load all
    # Using 100k rows for speed in this demo context if needed, but let's try full load
    # or a robust sample.
    df = pd.read_csv(normal_csv)
    df.columns = df.columns.str.strip()
    
    # Filter only Normal data
    if "Normal/Attack" in df.columns:
        df = df[df["Normal/Attack"] == "Normal"]
        df = df.drop(columns=["Normal/Attack"])
    
    # Drop Timestamp
    if "Timestamp" in df.columns:
        df = df.drop(columns=["Timestamp"])
        
    print(f"    Data Loaded: {df.shape}", flush=True)

    # 2. Feature Engineering (SMA)
    print("Generating Features (SMA)...", flush=True)
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    
    df_processed = df.copy()
    feature_cols = numeric_cols
    
    # Apply SMA
    for col in feature_cols:
        # FillNa with 0 specifically for the start or use min_periods=1
        df_processed[f"{col}_SMA"] = df[col].rolling(window=5, min_periods=1).mean()
    
    df_processed = df_processed.dropna()
    
    # Save Feature Columns List (Crucial for Inference alignment)
    final_columns = df_processed.columns.tolist()
    with open(COLUMNS_PATH, 'w') as f:
        json.dump(final_columns, f)
    print(f"    Features saved to {COLUMNS_PATH}", flush=True)
    
    X = df_processed.values
    
    # 3. Scaling & PCA
    print("Fitting Scalers & PCA...", flush=True)
    
    # 3.1 Robust Scaler
    scaler = RobustScaler()
    X_scaled = scaler.fit_transform(X)
    joblib.dump(scaler, SCALER_PATH)
    
    # 3.2 PCA
    pca = PCA(n_components=15) # Fixed based on notebook analysis
    X_pca = pca.fit_transform(X_scaled)
    joblib.dump(pca, PCA_PATH)
    
    # 3.3 PCA Scaler (StandardScaler)
    pca_scaler = StandardScaler()
    X_train_final = pca_scaler.fit_transform(X_pca)
    joblib.dump(pca_scaler, PCA_SCALER_PATH)
    
    print("    Pre-processing artifacts saved.", flush=True)

    # 4. Autoencoder Training
    print("Training Autoencoder...", flush=True)
    input_dim = X_train_final.shape[1]
    autoencoder = build_autoencoder_scientific(input_dim, 0.5)
    autoencoder.compile(optimizer='adam', loss='mse')
    
    early_stop = EarlyStopping(monitor='val_loss', patience=5, restore_best_weights=True)
    
    # Train
    autoencoder.fit(
        X_train_final, X_train_final,
        epochs=30, # Reduced for speed, usually 50-100
        batch_size=512,
        validation_split=0.1,
        callbacks=[early_stop],
        verbose=1
    )
    
    # Save Full Model
    autoencoder.save(MODEL_PATH)
    # Save Weights
    autoencoder.save_weights(WEIGHTS_PATH)
    print(f"    Saved model to {MODEL_PATH}", flush=True)

    # 5. Isolation Forest Training
    print("Training Isolation Forest...", flush=True)
    iso_forest = IsolationForest(contamination=0.01, random_state=42, n_jobs=-1)
    iso_forest.fit(X_train_final)
    joblib.dump(iso_forest, ISO_FOREST_PATH)
    print("    Saved Isolation Forest.", flush=True)

    # 6. Threshold Calculation
    print("Calculating Thresholds (99.9th Percentile)...", flush=True)
    train_recon = autoencoder.predict(X_train_final)
    train_mse = np.mean(np.power(X_train_final - train_recon, 2), axis=1)
    
    ae_threshold = float(np.percentile(train_mse, 99.9))
    
    # Guardrail
    if ae_threshold < 0.1:
         print("[!] Warning: Threshold too tight. Adjusting...")
         ae_threshold = max(ae_threshold, float(np.mean(train_mse) + 5 * np.std(train_mse)))
    
    iso_scores_train = iso_forest.decision_function(X_train_final)
    iso_threshold = float(np.percentile(iso_scores_train, 1)) # 1st percentile for anomalies

    print(f"[*] New Robust Threshold (99.9%): {ae_threshold:.5f}", flush=True)
    print(f"[*] ISO FOREST THRESHOLD (1st): {iso_threshold:.5f}", flush=True)

    threshold_data = {
        "ae_threshold": ae_threshold,
        "iso_threshold": iso_threshold,
        "h_factor": 0.5,
        "threshold_type": "Data-Driven (99.9th Percentile)",
        "training_date": datetime.datetime.now().isoformat()
    }
    
    with open(THRESHOLD_PATH, 'w') as f:
        json.dump(threshold_data, f, indent=4)
    
    print(f"[*] Configuration saved to {THRESHOLD_PATH}", flush=True)
    print("Training Pipeline Complete.")

if __name__ == "__main__":
    main()
