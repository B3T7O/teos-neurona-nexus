#!/usr/bin/env python3
import json
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
CHAMPION_FILE = ROOT / "data" / "processed" / "evolve_champion.json"
PRED_FILE = ROOT / "data" / "processed" / "learning_predictions_v2.jsonl"
OUTPUT_FILE = ROOT / "data" / "processed" / "evolve_live_prediction.json"

def get_latest_predictions():
    preds = {}
    if not PRED_FILE.exists(): return preds
    with PRED_FILE.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            try:
                p = json.loads(line)
                method = p.get("method")
                if method:
                    preds[method] = p.get("predicted_hashRate_GHs")
            except: pass
    return preds

def main():
    if not CHAMPION_FILE.exists():
        print("⏳ No hay Campeón Evolutivo aún. Ejecuta evolve_lab.py primero.")
        return

    with CHAMPION_FILE.open("r", encoding="utf-8") as f:
        champion = json.load(f)
    
    weights = champion.get("weights", {})
    latest_preds = get_latest_predictions()
    
    total_prediction = 0.0
    total_weight_used = 0.0
    details = {}

    for method, weight in weights.items():
        if method in latest_preds:
            pred = latest_preds[method]
            total_prediction += pred * weight
            total_weight_used += weight
            details[method] = {"weight": weight, "prediction": pred}
        else:
            print(f"⚠️ El método '{method}' no tiene predicciones recientes. Saltando...")

    if total_weight_used > 0:
        # Normalizar por si falta algún método
        final_pred = total_prediction / total_weight_used
        
        output = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "evolve_champion_ape": champion.get("ape_mean"),
            "combined_prediction_GHs": round(final_pred, 2),
            "weights_used": details
        }
        
        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with OUTPUT_FILE.open("w", encoding="utf-8") as f:
            json.dump(output, f, indent=2)
            
        print(f"✅ Predicción del Campeón Evolutivo: {final_pred:.2f} GH/s")
    else:
        print("❌ No se pudo calcular la predicción (faltan datos).")

if __name__ == "__main__":
    main()
