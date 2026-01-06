import os
import sys
import datetime
from datetime import datetime
import json
import pandas as pd
import numpy as np
import joblib
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


if not os.path.exists(MODEL_DIR):
    os.makedirs(MODEL_DIR)

PROCEED_DIR = os.path.join(DATA_DIR, "proceed")
if not os.path.exists(PROCEED_DIR):
    os.makedirs(PROCEED_DIR)

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

# File paths
NORMAL_DATA_PATH = os.path.join(DATA_DIR, 'normal.csv')
ATTACK_DATA_PATH = os.path.join(DATA_DIR, 'attack.csv')
MODEL_PATH = os.path.join(MODEL_DIR, 'model.keras')
SCALER_PATH = os.path.join(MODEL_DIR, 'scaler.pkl')
PCA_PATH = os.path.join(MODEL_DIR, 'pca.pkl')
PCA_SCALER_PATH = os.path.join(MODEL_DIR, 'pca_scaler.pkl')
ISO_FOREST_PATH = os.path.join(MODEL_DIR, 'iso_forest.pkl')
THRESHOLD_PATH = os.path.join(MODEL_DIR, 'threshold.json')
MODEL_COLUMNS_PATH = os.path.join(MODEL_DIR, 'model_columns.json')

# Startup Rows to remove (6 hours of data at 1Hz)
STARTUP_ROWS = 21600

def main():
    print("[*] Starting Production Training Pipeline...", flush=True)
    
    print("Loading datasets...", flush=True)
    df_normal = pd.read_csv(NORMAL_DATA_PATH, low_memory=False)
    df_attack = pd.read_csv(ATTACK_DATA_PATH, low_memory=False)
    
    # 1. Column Clean-up
    df_normal.columns = df_normal.columns.str.strip()
    df_attack.columns = df_attack.columns.str.strip()
    
    # 2. Startup row removal (Scientific refinement)
    print(f"Removing first {STARTUP_ROWS} rows from normal data...", flush=True)
    df_normal = df_normal.iloc[STARTUP_ROWS:].reset_index(drop=True)
    
    # Concatenate for preprocessing (but keep normal for fitting)
    print(f"Normal: {len(df_normal)}, Attack: {len(df_attack)}", flush=True)
    df_normal['Is_Attack'] = 0
    df_attack['Is_Attack'] = 1
    full_df = pd.concat([df_normal, df_attack], axis=0)
    
    # Drop rows with NaN values (Scientific refinement)
    initial_len = len(full_df)
    full_df = full_df.dropna()
    print(f"Dropped {initial_len - len(full_df)} rows with NaN values. Remaining: {len(full_df)}", flush=True)

    # --- SAVE PROCESSED DATA FOR DASHBOARD ---
    print(f"[*] Saving processed data to {PROCEED_DIR}...", flush=True)
    # Split back based on Is_Attack
    clean_normal = full_df[full_df['Is_Attack'] == 0].drop(columns=['Is_Attack'])
    clean_attack = full_df[full_df['Is_Attack'] == 1].drop(columns=['Is_Attack'])
    
    clean_normal.to_csv(os.path.join(PROCEED_DIR, "normal.csv"), index=False)
    clean_attack.to_csv(os.path.join(PROCEED_DIR, "attack.csv"), index=False)
    print(f"    Saved cleaned normal.csv ({len(clean_normal)} rows)", flush=True)
    print(f"    Saved cleaned attack.csv ({len(clean_attack)} rows)", flush=True)
    # ----------------------------------------
    
    # Drop Timestamp and Label for feature extraction
    exclude_cols = ['Timestamp', 'timestamp', 'Normal/Attack', 'Is_Attack']
    feature_cols = [c for c in full_df.columns if c not in exclude_cols]
    
    X = full_df[feature_cols].apply(pd.to_numeric, errors='coerce').fillna(0)
    
    # Separate back to normal (training) and mixed
    X_train_raw = X[full_df['Is_Attack'] == 0].copy()
    X_test_raw = X[full_df['Is_Attack'] == 1].copy()

    # 3. Identify and Remove Constant Columns (Zero Variance)
    print("Removing zero-variance columns...")
    variances = X_train_raw.var()
    constant_cols = variances[variances == 0].index.tolist()
    if constant_cols:
        print(f"Dropping {len(constant_cols)} constant columns: {constant_cols}")
        X_train_raw = X_train_raw.drop(columns=constant_cols)
        X_test_raw = X_test_raw.drop(columns=constant_cols)
    
    base_cols = X_train_raw.columns.tolist()
    
    # 4. SMA Feature Engineering (Wait until after dropping constants)
    WINDOW_SIZE = 5
    print(f"Adding SMA features (window={WINDOW_SIZE})...")
    for col in base_cols:
        X_train_raw[f'{col}_SMA'] = X_train_raw[col].rolling(window=WINDOW_SIZE, min_periods=1).mean()
        X_test_raw[f'{col}_SMA'] = X_test_raw[col].rolling(window=WINDOW_SIZE, min_periods=1).mean()
        
    # Standard: fill SMA NaNs with 0 (usually at start of series)
    X_train_raw = X_train_raw.fillna(0)
    X_test_raw = X_test_raw.fillna(0)
    
    model_columns = X_train_raw.columns.tolist()
    with open(MODEL_COLUMNS_PATH, 'w') as f:
        json.dump(model_columns, f)

    print(f"[*] Final X_train_raw shape: {X_train_raw.shape}", flush=True)
    print(f"[*] Final X_test_raw shape: {X_test_raw.shape}", flush=True)

    # 5. Scaling (Robust -> PCA -> Standard)
    print("Fitting Scalers and PCA...", flush=True)
    scaler = RobustScaler()
    X_train_scaled = scaler.fit_transform(X_train_raw)
    
    pca = PCA(n_components=15, random_state=42)
    X_train_pca = pca.fit_transform(X_train_scaled)
    
    pca_scaler = StandardScaler()
    X_train_final = pca_scaler.fit_transform(X_train_pca)
    
    # Save artifacts
    joblib.dump(scaler, SCALER_PATH)
    joblib.dump(pca, PCA_PATH)
    joblib.dump(pca_scaler, PCA_SCALER_PATH)

    # 6. Autoencoder Training
    print("Training Autoencoder...", flush=True)
    input_dim = X_train_final.shape[1]
    autoencoder = build_autoencoder_scientific(input_dim, 0.5)
    autoencoder.compile(optimizer='adam', loss='mse')
    
    early_stop = EarlyStopping(monitor='val_loss', patience=5, restore_best_weights=True)
    autoencoder.fit(
        X_train_final, X_train_final,
        epochs=50,
        batch_size=512,
        validation_split=0.1,
        callbacks=[early_stop],
        verbose=1
    )
    autoencoder.save(MODEL_PATH)

    # 7. Isolation Forest Training
    print("Training Isolation Forest...", flush=True)
    iso_forest = IsolationForest(contamination=0.01, random_state=42, n_jobs=-1)
    iso_forest.fit(X_train_final)
    # Save isolation forest
    joblib.dump(iso_forest, ISO_FOREST_PATH)

    # 8. Threshold Calculation (Scientific refinement: 99.9th percentile)
    print("Calculating thresholds...", flush=True)
    # Re-calculate on training data
    train_recon = autoencoder.predict(X_train_final)
    train_mse = np.mean(np.power(X_train_final - train_recon, 2), axis=1)
    
    # 99.9th percentile as validated in scientific notebook
    ae_threshold = float(np.percentile(train_mse, 99.9))
    
    # Isolation Forest scores (lower = more anomalous)
    iso_scores_train = iso_forest.decision_function(X_train_final)
    iso_threshold = float(np.percentile(iso_scores_train, 1))

    print(f"[*] MSE Distribution: Mean={np.mean(train_mse):.5f}, Max={np.max(train_mse):.5f}", flush=True)
    print(f"[*] Percentile Options: 95th={np.percentile(train_mse, 95):.5f}, 99th={np.percentile(train_mse, 99):.5f}, 99.9th={np.percentile(train_mse, 99.9):.5f}", flush=True)
    print(f"[*] AUTOENCODER THRESHOLD (99.9th): {ae_threshold:.5f}", flush=True)
    print(f"[*] ISO FOREST THRESHOLD (1st): {iso_threshold:.5f}", flush=True)

    threshold_data = {
        "ae_threshold": ae_threshold,
        "iso_threshold": iso_threshold,
        "h_factor": 0.5,
        "training_date": datetime.now().isoformat()
    }
    
    with open(THRESHOLD_PATH, 'w') as f:
        json.dump(threshold_data, f, indent=4)
    print(f"[*] New thresholds saved to {THRESHOLD_PATH}", flush=True)
    print(f" Training Complete. Artifacts saved in {MODEL_DIR}", flush=True)
    print(f"   Autoencoder Threshold: {ae_threshold:.6f}", flush=True)
    print(f"   Isolation Forest Threshold: {iso_threshold:.6f}", flush=True)


if __name__ == "__main__":
    main()
