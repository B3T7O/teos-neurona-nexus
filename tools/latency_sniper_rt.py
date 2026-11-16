#!/usr/bin/env python3
import json
import urllib.request
import time
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
LOG_FILE = ROOT / "data" / "processed" / "axeos_logs.json"
OUTPUT_FILE = ROOT / "data" / "processed" / "latency_sniper_rt.jsonl"
API = "https://mempool.space/api"

def fetch_text(url):
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return r.read().decode().strip()
    except Exception:
        return None

def fetch_json(url):
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return json.loads(r.read())
    except Exception:
        return None

def parse_ts(ts_str):
    try:
        if ts_str.endswith("Z"):
            ts_str = ts_str[:-1] + "+00:00"
        return datetime.fromisoformat(ts_str).timestamp()
    except Exception:
        return None

def get_last_block_height():
    blocks = fetch_text(f"{API}/blocks/tip/height")
    return int(blocks) if blocks else None

def find_task_for_block(block_time, new_height):
    for retry in range(10):
        if LOG_FILE.exists():
            with LOG_FILE.open("r", encoding="utf-8", errors="ignore") as f:
                logs = json.load(f)
            for log_entry in reversed(logs):
                msg = log_entry.get("message", "")
                if "mining.notify" in msg or "clean_jobs" in msg:
                    task_time = parse_ts(log_entry.get("ts"))
                    if task_time:
                        delta = task_time - block_time
                        if 0 < delta < 15:
                            return task_time, delta, log_entry.get("ts")
        time.sleep(2)
    return None, None, None

def main():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🎯 LATENCY SNIPER iniciado. Modo continuo.")
    
    last_height = get_last_block_height()
    if last_height is None:
        print("❌ No se pudo conectar con mempool.space. Reintentando en 30s...")
        time.sleep(30)
        return main()
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 📦 Altura actual: #{last_height}. Esperando el siguiente bloque...")

    while True:
        try:
            time.sleep(5)
            new_height = get_last_block_height()
            
            if not new_height:
                continue
            
            if new_height > last_height:
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 🚨 ¡BLOQUE MINADO! #{new_height}")
                
                block_info = None
                for attempt in range(10):
                    block_hash = fetch_text(f"{API}/block-height/{new_height}")
                    if block_hash:
                        block_info = fetch_json(f"{API}/block/{block_hash}")
                        if block_info and "timestamp" in block_info:
                            break
                    time.sleep(3)
                
                if not block_info:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ No se pudo obtener info del bloque. Continuando...")
                    last_height = new_height
                    continue
                
                block_time = block_info.get("timestamp")
                task_time, delta, task_iso = find_task_for_block(block_time, new_height)
                
                if delta is not None:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Latencia: {delta*1000:.0f} ms")
                    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
                    with OUTPUT_FILE.open("a", encoding="utf-8") as f_out:
                        f_out.write(json.dumps({
                            "block_height": new_height,
                            "block_time": block_time,
                            "task_time": task_time,
                            "latency_ms": round(delta * 1000, 2)
                        }) + "\n")
                else:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️ No se encontró tarea para el bloque #{new_height}")
                
                last_height = new_height
        
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Error: {e}. Reintentando en 30s...")
            time.sleep(30)

if __name__ == "__main__":
    main()
