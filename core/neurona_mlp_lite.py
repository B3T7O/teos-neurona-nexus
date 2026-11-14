#!/usr/bin/env python3
# TEOS Neurona Nexus - MLP Lite (Integrado al Learning Loop)
import json
import time
import numpy as np
from pathlib import Path
from datetime import datetime, timezone

BASE_DIR = Path(__file__).resolve().parent.parent
INPUT_FILE = BASE_DIR / "data/raw/bitaxe_samples.marked.jsonl"
# AHORA ESCRIBIMOS EN LA LIBRETA GENERAL DE PREDICCIONES
OUTPUT_FILE = BASE_DIR / "data/processed/learning_predictions_v2.jsonl"

# Arquitectura de la Red Neuronal
INPUT_SIZE = 3
HIDDEN_SIZE = 8
OUTPUT_SIZE = 1
LEARNING_RATE = 0.01

def load_recent_data(n=100):
    if not INPUT_FILE.exists(): return []
    samples = []
    with INPUT_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                o = json.loads(line)
                if o.get("quality") == "ok" and "temp" in o and "hashRate" in o and "vrTemp" in o:
                    samples.append(o)
            except: pass
    return samples[-n:] if len(samples) >= n else []

def train_and_predict():
    samples = load_recent_data(100)
    if len(samples) < 20:
        return {"status": "waiting_for_data", "msg": f"Faltan datos ({len(samples)}/20)"}

    X = np.array([[s["temp"], s["vrTemp"], s["hashRate"]] for s in samples])
    Y = np.array([[s["hashRate"]] for s in samples])
    
    X_mean, X_std = X.mean(axis=0), X.std(axis=0) + 1e-8
    X_norm = (X - X_mean) / X_std
    Y_mean, Y_std = Y.mean(), Y.std() + 1e-8
    Y_norm = (Y - Y_mean) / Y_std

    np.random.seed(42)
    W1 = np.random.randn(INPUT_SIZE, HIDDEN_SIZE) * np.sqrt(2.0 / INPUT_SIZE)
    W2 = np.random.randn(HIDDEN_SIZE, OUTPUT_SIZE) * np.sqrt(2.0 / HIDDEN_SIZE)

    epochs = 200
    for epoch in range(epochs):
        Z1 = np.dot(X_norm, W1)
        A1 = np.maximum(0, Z1)
        Z2 = np.dot(A1, W2)
        
        dZ2 = Z2 - Y_norm
        dW2 = np.dot(A1.T, dZ2) / len(X_norm)
        dA1 = np.dot(dZ2, W2.T)
        dZ1 = dA1 * (Z1 > 0)
        dW1 = np.dot(X_norm.T, dZ1) / len(X_norm)
        
        W2 -= LEARNING_RATE * dW2
        W1 -= LEARNING_RATE * dW1

    last_X = np.array([X[-1]])
    last_X_norm = (last_X - X_mean) / X_std
    pred_Z1 = np.dot(last_X_norm, W1)
    pred_A1 = np.maximum(0, pred_Z1)
    pred_Z2 = np.dot(pred_A1, W2)
    pred_norm = pred_Z2[0][0]
    
    pred_real = (pred_norm * Y_std) + Y_mean
    
    # Formato EXACTO que espera learning_loop_v2.py
    timestamp = datetime.now(timezone.utc).isoformat()
    return {
        "prediction_id": f"{timestamp}|mlp_lite",
        "source_timestamp": timestamp,
        "method": "mlp_lite",
        "predicted_hashRate_GHs": float(pred_real),
        "current_hashRate_GHs": float(X[-1][2])
    }

if __name__ == "__main__":
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Entrenando MLP Lite...")
    result = train_and_predict()
    
    if "status" not in result:
        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with OUTPUT_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(result) + "\n")
        print(f"✅ Predicción enviada al Learning Loop: {result['predicted_hashRate_GHs']:.2f} GH/s")
    else:
        print(f"⚠️ {result['msg']}")
