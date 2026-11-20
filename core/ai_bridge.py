#!/usr/bin/env python3
import json
import urllib.request
from pathlib import Path
from datetime import datetime, timezone
import os, time

ROOT = Path(__file__).resolve().parent.parent
PRED_PATH = ROOT / "data/processed/learning_predictions_v2.jsonl"
LOG_PATH = ROOT / "data/processed/ai_bridge_log.jsonl"
BITAXE_URL = "http://192.168.18.45/api/system/info"

# Límites de Seguridad (El Cinturón)
MIN_FREQ = 575
MAX_FREQ = 600
MAX_CHANGE = 5  # ±5 MHz por ciclo
MIN_CONFIDENCE = 0.8  # 3% de diferencia mínima para actuar


def get_evolve_prediction():
    evolve_path = ROOT / "data" / "processed" / "evolve_live_prediction.json"
    if not evolve_path.exists(): return None
    try:
        with evolve_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("combined_prediction_GHs")
    except Exception:
        return None

def get_latest_prediction():

    if not PRED_PATH.exists(): return None
    with PRED_PATH.open("r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()
        for line in reversed(lines):
            try:
                p = json.loads(line)
                if p.get("method") == "mlp_lite":
                    return p.get("predicted_hashRate_GHs")
            except: continue
    return None

def get_current_state():
    with urllib.request.urlopen(BITAXE_URL, timeout=5) as r:
        return json.loads(r.read())

def apply_change(new_freq, reason):
    payload = json.dumps({"frequency": new_freq}).encode()
    req = urllib.request.Request(
        "http://192.168.18.45/api/system",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="PATCH"
    )
    with urllib.request.urlopen(req, timeout=5) as r:
        if r.status == 200:
            print(f"✅ IA aplicó cambio: {new_freq} MHz ({reason})")
            LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with LOG_PATH.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"timestamp": datetime.now(timezone.utc).isoformat(), "new_freq": new_freq, "reason": reason}) + "\n")


def get_last_change_time():
    if not LOG_PATH.exists(): return None
    with LOG_PATH.open("r", encoding="utf-8") as f:
        lines = f.readlines()
        if not lines: return None
        try:
            last = json.loads(lines[-1])
            ts = last.get("timestamp")
            if ts:
                return datetime.fromisoformat(ts)
        except: pass
    return None

def main():
    # Verificar Cooldown (15 minutos)
    last_change = get_last_change_time()
    if last_change:
        now = datetime.now(timezone.utc)
        if last_change.tzinfo is None:
            last_change = last_change.replace(tzinfo=timezone.utc)
        elapsed = (now - last_change).total_seconds()
        if elapsed < 180: # 3 minutos (Reacción rápida)
            print(f"⏸️ IA en cooldown. Último cambio hace {elapsed/60:.1f} min. Esperando para evitar ruido.")
            return

    # Intentar leer al Campeón Evolutivo primero
    pred = get_evolve_prediction()
    
    if pred is not None:
        print("🧬 Usando predicción del Campeón Evolutivo.")
    else:
        print("🤖 Campeón no disponible. Usando predicción del MLP Lite.")
        pred = get_latest_prediction()
    if pred is None:
        print("⏳ Sin predicciones de la IA. Esperando...")
        return

    try:
        state = get_current_state()
    except Exception as e:
        print(f"❌ Error conectando al Bitaxe: {e}")
        return

    current_hr = state.get("hashRate_10m", 0)
    current_freq = state.get("actualFrequency", 580)
    
    # RESCATE: Si estamos por debajo del mínimo, subir inmediatamente
    if current_freq < MIN_FREQ:
        print(f"🛡️ Rescate: Freq actual ({current_freq}) < MIN_FREQ ({MIN_FREQ}). Subiendo a {MIN_FREQ}.")
        apply_change(MIN_FREQ, "Rescate de límite mínimo")
        with open("data/processed/last_freq_change.txt", "w") as f: f.write(str(time.time()))
        return

    temp = state.get("temp", 0)
    vr_temp = state.get("vrTemp", 0)
    error = state.get("errorPercentage", 0)

    # 1. Verificar seguridad del hardware
    if temp > 58 or vr_temp > 72 or error > 1.5:
        print(f"🛡️ IA bloqueada por seguridad (Temp={temp}°C, VRM={vr_temp}°C, Err={error}%)")
        return

    # 2. Calcular diferencia porcentual
    if current_hr == 0: return
    diff_pct = ((pred - current_hr) / current_hr) * 100

    # 2.1. Límite de Cordura (Sanity Check): Ignorar outliers absurdos (> 15%)
    if abs(diff_pct) > 15.0:
        print(f"⚠️ IA ignoró predicción absurda (diff={diff_pct:.1f}%). Posible outlier de datos.")
        return

    # 2.2. Periodo de Enfriamiento (Cooldown): Máximo 1 cambio cada 30 minutos
    cooldown_file = "data/processed/last_freq_change.txt"
    cooldown_seconds = 30 * 60  # 30 minutos
    now = time.time()
    
    if os.path.exists(cooldown_file):
        with open(cooldown_file, 'r') as f:
            last_change = float(f.read().strip())
        if now - last_change < cooldown_seconds:
            mins_left = int((cooldown_seconds - (now - last_change)) / 60)
            print(f"⏳ IA en periodo de enfriamiento. Esperar {mins_left} min antes del próximo ajuste.")
            return

    # 3. Decidir acción (solo cambios pequeños)
    if diff_pct > MIN_CONFIDENCE and current_freq < MAX_FREQ:
        new_freq = min(current_freq + MAX_CHANGE, MAX_FREQ)
        if new_freq != current_freq:
            apply_change(new_freq, f"IA predice +{diff_pct:.1f}% → +5 MHz")
            with open("data/processed/last_freq_change.txt", "w") as f: f.write(str(time.time()))
    elif diff_pct < -MIN_CONFIDENCE and current_freq > MIN_FREQ:
        new_freq = max(current_freq - MAX_CHANGE, MIN_FREQ)
        if new_freq != current_freq:
            apply_change(new_freq, f"IA predice {diff_pct:.1f}% → -5 MHz")
            with open("data/processed/last_freq_change.txt", "w") as f: f.write(str(time.time()))
    else:
        print(f"⏸️ IA no actúa (diff={diff_pct:.1f}%, freq={current_freq} MHz)")

if __name__ == "__main__":
    main()
