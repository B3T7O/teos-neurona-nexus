#!/usr/bin/env python3
# TEOS Neurona Nexus - MLP Lite (Con Memoria Estable)
import json
import time
import numpy as np
import re
from pathlib import Path
from datetime import datetime, timezone

BASE_DIR = Path(__file__).resolve().parent.parent
INPUT_FILE = BASE_DIR / "data" / "raw" / "bitaxe_samples.marked.jsonl"
LOG_FILE = BASE_DIR / "data" / "processed" / "axeos_logs.json"
OUTPUT_FILE = BASE_DIR / "data" / "processed" / "learning_predictions_v2.jsonl"
MODEL_FILE = BASE_DIR / "data" / "processed" / "model_weights.json"

INPUT_SIZE = 10
HIDDEN_SIZE = 12
OUTPUT_SIZE = 1
LEARNING_RATE = 0.005  # Reducido para mayor estabilidad

def get_regex_features():
    if not LOG_FILE.exists(): return 0, 0.0
    pattern = re.compile(r"Nonce\s+([A-Fa-f0-9]+)\s+diff\s+([\d\.]+)")
    share_count = 0
    diffs = []
    try:
        with LOG_FILE.open("r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
            try:
                logs = json.loads(content)
                if not isinstance(logs, list): logs = []
            except: logs = []
            for entry in logs[-500:]:
                if isinstance(entry, dict) and entry.get("category") == "asic_result":
                    match = pattern.search(entry.get("message", ""))
                    if match:
                        share_count += 1
                        diffs.append(float(match.group(2)))
    except: pass
    return share_count, (sum(diffs) / len(diffs) if diffs else 0.0)

def get_live_error_rates():
    import urllib.request
    try:
        with urllib.request.urlopen("http://192.168.18.45/api/system/info", timeout=5) as r:
            d = json.loads(r.read())
            reasons = d.get("sharesRejectedReasons", [])
            accepted = d.get("sharesAccepted", 1) or 1
            stale = next((x["count"] for x in reasons if x.get("message") == "Stale"), 0)
            duplicate = next((x["count"] for x in reasons if x.get("message") == "Duplicate"), 0)
            above = next((x["count"] for x in reasons if x.get("message") == "Above target"), 0)
            return (stale / accepted) * 100, (duplicate / accepted) * 100, (above / accepted) * 100
    except: return 0.0, 0.0, 0.0

def load_recent_data(n=300):
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
    samples = load_recent_data(300)
    if len(samples) < 20:
        return {"status": "waiting_for_data", "msg": f"Faltan datos ({len(samples)}/20)"}

    share_count, avg_diff = get_regex_features()
    stale_rate, dup_rate, above_rate = get_live_error_rates()

    X = np.array([
        [s.get("temp", 0), s.get("vrTemp", 0), s.get("hashRate", 0),
         s.get("hashRate_10m", s.get("hashRate", 0)), s.get("errorPercentage", 0),
         share_count, avg_diff, stale_rate, dup_rate, above_rate] for s in samples
    ])
    Y = np.array([[s["hashRate"]] for s in samples])

    # 1. Cargar memoria (si existe) o calcular normalización nueva
    if MODEL_FILE.exists():
        try:
            with MODEL_FILE.open("r", encoding="utf-8") as f:
                mem = json.load(f)
            W1 = np.array(mem["W1"])
            W2 = np.array(mem["W2"])
            X_mean = np.array(mem["X_mean"])
            X_std = np.array(mem["X_std"])
            Y_mean = mem["Y_mean"]
            Y_std = mem["Y_std"]
            print("🧠 Memoria cargada: Continuando desde el aprendizaje anterior.")
        except Exception as e:
            print(f"⚠️ Error cargando memoria: {e}. Iniciando desde cero.")
            X_mean, X_std = X.mean(axis=0), X.std(axis=0) + 1e-8
            Y_mean, Y_std = Y.mean(), Y.std() + 1e-8
            np.random.seed(42)
            W1 = np.random.randn(INPUT_SIZE, HIDDEN_SIZE) * np.sqrt(2.0 / INPUT_SIZE)
            W2 = np.random.randn(HIDDEN_SIZE, OUTPUT_SIZE) * np.sqrt(2.0 / HIDDEN_SIZE)
    else:
        print("🆕 No hay memoria previa. Iniciando red neuronal desde cero.")
        X_mean, X_std = X.mean(axis=0), X.std(axis=0) + 1e-8
        Y_mean, Y_std = Y.mean(), Y.std() + 1e-8
        np.random.seed(42)
        W1 = np.random.randn(INPUT_SIZE, HIDDEN_SIZE) * np.sqrt(2.0 / INPUT_SIZE)
        W2 = np.random.randn(HIDDEN_SIZE, OUTPUT_SIZE) * np.sqrt(2.0 / HIDDEN_SIZE)

    # 2. Normalizar usando la normalización cargada
    X_norm = (X - X_mean) / X_std
    Y_norm = (Y - Y_mean) / Y_std

    # 3. Entrenar con clipping de pesos
    epochs = 100
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
        # Clipping para evitar explosión
        W1 = np.clip(W1, -5.0, 5.0)
        W2 = np.clip(W2, -5.0, 5.0)

    # 4. Predecir
    last_X = (X[-1:] - X_mean) / X_std
    pred_Z1 = np.dot(last_X, W1)
    pred_A1 = np.maximum(0, pred_Z1)
    pred_Z2 = np.dot(pred_A1, W2)
    pred_real = (pred_Z2[0][0] * Y_std) + Y_mean

    # 5. Guardar memoria (con la normalización usada)
    try:
        with MODEL_FILE.open("w", encoding="utf-8") as f:
            json.dump({
                "W1": W1.tolist(), "W2": W2.tolist(),
                "X_mean": X_mean.tolist(), "X_std": X_std.tolist(),
                "Y_mean": float(Y_mean), "Y_std": float(Y_std)
            }, f)
    except Exception as e:
        print(f"⚠️ Error guardando memoria: {e}")

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
        print(f"✅ Predicción: {result['predicted_hashRate_GHs']:.2f} GH/s")
    else:
        print(f"⚠️ {result['msg']}")
