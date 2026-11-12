#!/usr/bin/env python3
"""
Genera el pulso de Bitcoin en vivo (epoch actual).
Guarda los datos en data/processed/live_pulse.json
"""
import json
import urllib.request
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "data" / "processed" / "live_pulse.json"
API = "https://mempool.space/api"

def fetch_json(url):
    with urllib.request.urlopen(url, timeout=15) as r:
        return json.loads(r.read())

def main():
    print("[1] Obteniendo datos del epoch actual...")
    diff = fetch_json(f"{API}/v1/difficulty-adjustment")
    
    progress = diff.get("progressPercent", 0)
    change = diff.get("difficultyChange", 0)
    remaining_blocks = diff.get("remainingBlocks", 0)
    time_avg_min = diff.get("timeAvg", 600000) / 60000
    next_height = diff.get("nextRetargetHeight", 0)
    
    # Calcular la "salud" del pulso
    if time_avg_min < 9.0:
        pulse_status = "RÁPIDO"
        pulse_color = "yellow"
    elif time_avg_min > 11.0:
        pulse_status = "LENTO"
        pulse_color = "red"
    else:
        pulse_status = "NORMAL"
        pulse_color = "green"
    
    print(f"    Progreso: {progress:.1f}%")
    print(f"    Tiempo promedio: {time_avg_min:.2f} min")
    print(f"    Cambio estimado: {change:+.2f}%")
    print(f"    Bloques restantes: {remaining_blocks}")
    print(f"    Estado: {pulse_status}")
    
    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "progress_pct": round(progress, 2),
        "avg_block_time_min": round(time_avg_min, 2),
        "estimated_change_pct": round(change, 2),
        "remaining_blocks": remaining_blocks,
        "next_retarget_height": next_height,
        "pulse_status": pulse_status,
        "pulse_color": pulse_color
    }
    
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    
    print(f"\n✅ Datos guardados en {OUTPUT}")

if __name__ == "__main__":
    main()
