#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = ROOT / "data" / "processed" / "integrity_state.json"
ALERT_FILE = ROOT / "data" / "processed" / "integrity_alerts.jsonl"

# Archivos a auditar
FILES_TO_CHECK = {
    "outcomes": ROOT / "data" / "processed" / "learning_outcomes_v2.jsonl",
    "predictions": ROOT / "data" / "processed" / "learning_predictions_v2.jsonl"
}

def get_file_hash(filepath):
    """Calcula el hash SHA-256 de un archivo de forma rápida y sin usar RAM."""
    if not filepath.exists(): return None
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hasher.update(chunk)
    return hasher.hexdigest()

def main():
    current_state = {}
    for name, path in FILES_TO_CHECK.items():
        current_state[name] = get_file_hash(path)

    previous = {}
    if STATE_FILE.exists():
        try:
            previous = json.loads(STATE_FILE.read_text())
        except: pass

    alert = None
    for name, current_hash in current_state.items():
        prev_hash = previous.get(name)
        if prev_hash and current_hash and prev_hash != current_hash:
            # Es normal si el archivo creció (nuevos datos)
            current_size = FILES_TO_CHECK[name].stat().st_size
            prev_size = previous.get(f"{name}_size", 0)
            if current_size < prev_size:
                alert = f"🚨 ALERTA: {name} se hizo más pequeño. Posible manipulación."
                print(alert)
            else:
                print(f"✅ {name} actualizado normalmente (nuevos datos).")

    # Guardar estado
    for name, path in FILES_TO_CHECK.items():
        if path.exists():
            current_state[f"{name}_size"] = path.stat().st_size
            
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(current_state, indent=2))

    if alert:
        ALERT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with ALERT_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"timestamp": datetime.now(timezone.utc).isoformat(), "alert": alert}) + "\n")

if __name__ == "__main__":
    main()
