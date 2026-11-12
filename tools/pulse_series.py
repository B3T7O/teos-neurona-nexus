#!/usr/bin/env python3
"""
Mantiene una serie temporal de los tiempos de bloque de Bitcoin.
Append-only: solo anade bloques nuevos, no duplica.
Guarda en data/processed/pulse_series.jsonl
"""
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "data" / "processed" / "pulse_series.jsonl"
API = "https://mempool.space/api"

def fetch_json(url):
    with urllib.request.urlopen(url, timeout=15) as r:
        return json.loads(r.read())

def fetch_text(url):
    with urllib.request.urlopen(url, timeout=15) as r:
        return r.read().decode().strip()

def load_existing():
    """Carga los heights ya guardados."""
    existing = {}
    if OUTPUT.exists():
        with open(OUTPUT) as f:
            for line in f:
                try:
                    o = json.loads(line)
                    existing[o["height"]] = o
                except:
                    pass
    return existing

def main():
    print("[1] Cargando serie existente...")
    existing = load_existing()
    print(f"    Ya tenemos {len(existing)} bloques guardados")
    
    print("[2] Obteniendo altura actual...")
    current = int(fetch_text(f"{API}/blocks/tip/height"))
    print(f"    Altura actual: {current}")
    
    # Descargar los ultimos 30 bloques (o solo los nuevos)
    new_count = 0
    to_fetch = []
    for h in range(current - 29, current + 1):
        if h not in existing and h > 0:
            to_fetch.append(h)
    
    print(f"[3] Descargando {len(to_fetch)} bloques nuevos...")
    
    prev_time = None
    if existing:
        # Necesitamos el tiempo del bloque anterior al primero a descargar
        min_h = min(to_fetch) if to_fetch else current
        prev_h = min_h - 1
        if prev_h in existing:
            prev_time = existing[prev_h]["timestamp"]
        else:
            try:
                bh = fetch_text(f"{API}/block-height/{prev_h}")
                b = fetch_json(f"{API}/block/{bh}")
                prev_time = b["timestamp"]
            except:
                prev_time = None
    
    with open(OUTPUT, "a") as f:
        for h in to_fetch:
            try:
                bh = fetch_text(f"{API}/block-height/{h}")
                b = fetch_json(f"{API}/block/{bh}")
                interval = (b["timestamp"] - prev_time) / 60 if prev_time else 10.0
                
                entry = {
                    "height": h,
                    "timestamp": b["timestamp"],
                    "interval_min": round(interval, 2),
                    "nonce": b.get("nonce", 0),
                }
                f.write(json.dumps(entry) + "\n")
                prev_time = b["timestamp"]
                new_count += 1
                print(f"  + Bloque {h} | {interval:.2f} min")
            except Exception as e:
                print(f"  ! Error bloque {h}: {e}")
    
    print(f"\n✅ {new_count} bloques nuevos guardados en {OUTPUT}")

if __name__ == "__main__":
    main()
