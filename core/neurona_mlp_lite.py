#!/usr/bin/env python3
# TEOS Neurona Nexus - MLP Lite (7 Features, sin Nonces, 12 Neuronas)
import json
import time
import numpy as np
import re
from pathlib import Path
from datetime import datetime, timezone

BASE_DIR = Path(__file__).resolve().parent.parent
INPUT_FILE = BASE_DIR / "data/raw/bitaxe_samples.marked.jsonl"
LOG_FILE = BASE_DIR / "data/processed/axeos_logs.json"
OUTPUT_FILE = BASE_DIR / "data/processed/learning_predictions_v2.jsonl"

# Arquitectura optimizada (Poda)
INPUT_SIZE = 10    # 10 sentidos (Ojo Clínico completo)
HIDDEN_SIZE = 12  # 12 neuronas (más humilde)
OUTPUT_SIZE = 1
LEARNING_RATE = 0.01

def get_regex_features():
    """Extrae shares y dificultad de los logs usando Regex (sin nonces)."""
    if not LOG_FILE.exists():
        return 0, 0.0

    pattern = re.compile(r"Nonce\s+([A-Fa-f0-9]+)\s+diff\s+([\d\.]+)")
    share_count = 0
    diffs = []

    try:
        with LOG_FILE.open("r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
            try:
                logs = json.loads(content)
                if not isinstance(logs, list):
                    logs = []
            except Exception:
                logs = []

            logs = logs[-500:]

            for entry in logs:
                if not isinstance(entry, dict):
                    continue
                if entry.get("category") != "asic_result":
                    continue
                message = entry.get("message", "")
                match = pattern.search(message)
                if match:
                    share_count += 1
                    diffs.append(float(match.group(2)))
    except Exception:
        pass

    avg_diff = sum(diffs) / len(diffs) if diffs else 0.0
    return share_count, avg_diff

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


def get_live_error_rates():
    import urllib.request
    try:
        with urllib.request.urlopen("http://192.168.18.45/api/system/info", timeout=5) as r:
            d = json.loads(r.read())
            reasons = d.get("sharesRejectedReasons", [])
            accepted = d.get("sharesAccepted", 1)
            if accepted == 0: accepted = 1
            
            stale = next((x["count"] for x in reasons if x.get("message") == "Stale"), 0)
            duplicate = next((x["count"] for x in reasons if x.get("message") == "Duplicate"), 0)
            above = next((x["count"] for x in reasons if x.get("message") == "Above target"), 0)
            
            return (stale / accepted) * 100, (duplicate / accepted) * 100, (above / accepted) * 100
    except Exception:
        return 0.0, 0.0, 0.0


def check_perfect_shares():
    import urllib.request
    try:
        with urllib.request.urlopen("http://192.168.18.45/api/system/info", timeout=5) as r:
            d = json.loads(r.read())
        error = float(d.get("errorPercentage", 1.0))
        shares = d.get("sharesAccepted", 0)
        
        if error < 0.01:
            PERFECT_LOG = BASE_DIR / "data" / "processed" / "perfect_shares.jsonl"
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error_rate": error,
                "shares_accepted": shares,
                "hashrate_10m": round(d.get("hashRate_10m", 0), 2),
                "frequency": d.get("actualFrequency", 0),
                "temp": d.get("temp", 0)
            }
            PERFECT_LOG.parent.mkdir(parents=True, exist_ok=True)
            with PERFECT_LOG.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
            print(f"🏆 ¡HITO PERFECTO! {shares} shares con 0.00% de error. Guardado en perfect_shares.jsonl")
        else:
            print(f"⏸️ Error actual: {error:.2f}% (Esperando el 0.00%)")
    except Exception as e:
        print(f"❌ Error verificando shares perfectos: {e}")

def train_and_predict():


    samples = load_recent_data(300)
    if len(samples) < 20:
        return {"status": "waiting_for_data", "msg": f"Faltan datos ({len(samples)}/20)"}

    share_count, avg_diff = get_regex_features()
    stale_rate, dup_rate, above_rate = get_live_error_rates()

    # 10 Features
    X = np.array([
        [
            s.get("temp", 0),
            s.get("vrTemp", 0),
            s.get("hashRate", 0),
            s.get("hashRate_10m", s.get("hashRate", 0)),
            s.get("errorPercentage", 0),
            share_count,
            avg_diff,
            stale_rate,
            dup_rate,
            above_rate
        ] for s in samples
    ])

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

    timestamp = datetime.now(timezone.utc).isoformat()
    return {
        "prediction_id": f"{timestamp}|mlp_lite",
        "source_timestamp": timestamp,
        "method": "mlp_lite",
        "predicted_hashRate_GHs": float(pred_real),
        "current_hashRate_GHs": float(X[-1][2])
    }

if __name__ == "__main__":
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Entrenando MLP Lite (12 neuronas, 10 features (Ojo Clínico))...")
    result = train_and_predict()

    if "status" not in result:
        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with OUTPUT_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(result) + "\n")
        print(f"✅ Predicción enviada al Learning Loop: {result['predicted_hashRate_GHs']:.2f} GH/s")
    else:
        print(f"⚠️ {result['msg']}")

    # --- VERIFICADOR DE SHARES PERFECTOS ---
    check_perfect_shares()

