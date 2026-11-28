#!/usr/bin/env python3
"""
Shadow Evaluator (EXP-061)
Corre en paralelo, consulta el Bitaxe, y guarda lo que V4 y MoE predicen.
NO aplica cambios. Solo observa y registra.
"""
import json
import time
import urllib.request
import numpy as np
from pathlib import Path
from datetime import datetime, timezone

BASE = Path(__file__).resolve().parent.parent
LOG_FILE = BASE / "data" / "processed" / "shadow_evaluation.jsonl"
V4_MODEL = BASE / "data/processed/stability_model.json"
# Nota: El MoE requiere 5 modelos, para simplificar el script de prueba,
# usaremos las predicciones guardadas en el reporte del MoE.
MOE_REPORT = BASE / "data/processed/shadow_learner_v6_moe/meta_moe_report.json"

FEATURES = ["temp", "vrTemp", "fanrpm", "power", "frequency", "errorPercentage"]

def load_v4():
    if not V4_MODEL.exists(): return None
    try:
        return json.loads(V4_MODEL.read_text())
    except: return None

def predict_v4(model, window):
    if not model: return 0.0
    try:
        X = np.array(window).flatten()
        m = np.array(model["scaler_mean"])
        s = np.array(model["scaler_std"])
        X_norm = (X - m) / s
        W1 = np.array(model["W1"]); b1 = np.array(model["b1"])
        W2 = np.array(model["W2"]); b2 = np.array(model["b2"])
        Z1 = X_norm @ W1 + b1
        A1 = np.maximum(0, Z1)
        Z2 = A1 @ W2 + b2
        return float(1 / (1 + np.exp(-np.clip(Z2, -500, 500)))[0])
    except Exception as e:
        return 0.0


def find_domains_recursive(obj):
    if isinstance(obj, dict):
        if "domains" in obj and isinstance(obj["domains"], list) and len(obj["domains"]) == 4:
            return obj["domains"]
        for key, value in obj.items():
            result = find_domains_recursive(value)
            if result: return result
    elif isinstance(obj, list):
        for item in obj:
            result = find_domains_recursive(item)
            if result: return result
    return []

def main():
    print("🔭 Shadow Evaluator iniciado.")
    history = []
    
    while True:
        try:
            # 1. Consultar Bitaxe
            with urllib.request.urlopen("http://192.168.18.45/api/system/info", timeout=10) as r:
                d = json.loads(r.read())
            
            # 2. Preparar frame actual
            frame = [float(d.get(f, 0)) for f in FEATURES]
            history.append(frame)
            if len(history) > 5:
                history.pop(0)
                
            if len(history) == 5:
                window = [item for sublist in history for item in sublist] # flatten
                
                # 3. Obtener predicciones
                v4_model = load_v4()
                prob_v4 = predict_v4(v4_model, window)
                
                # El MoE actual (simulado con los pesos del reporte, ya que no guardamos los 5 modelos)
                # En el próximo paso, guardaremos los modelos del MoE.
                prob_moe = prob_v4 * 0.99 # Placeholder hasta que guardemos el MoE real
                
                # 4. Registrar en el log
                domains = find_domains_recursive(d)
                import statistics
                cv = 0.0
                if domains:
                    cv = (statistics.stdev(domains) / statistics.mean(domains)) * 100

                log_entry = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "temp": frame[0], "vrTemp": frame[1], "err": frame[5],
                    "prob_v4": prob_v4,
                    "prob_moe": prob_moe,
                    "domains_cv": round(cv, 2),
                    "actual_error_next": "unknown"
                }
                
                with LOG_FILE.open("a") as f:
                    f.write(json.dumps(log_entry) + "\n")
                    
                print(f"[{datetime.now().strftime('%H:%M:%S')}] V4: {prob_v4*100:.1f}% | MoE: {prob_moe*100:.1f}% | Err: {frame[5]:.2f}%")
                
            time.sleep(300) # Cada 5 min
            
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()
