#!/usr/bin/env python3
"""
TEOS Evolve Runner v1.0
Ejecuta core/evolve_lab.py periodicamente y guarda el campeon.
- Por defecto: cada 6 horas.
- Modo simulacion: solo reporta cuando tocaria.
- Para ejecutar de verdad: --execute
- Log: data/evolve/evolve_log.jsonl
"""
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "data" / "evolve" / "evolve_log.jsonl"
CHAMPION = ROOT / "data" / "processed" / "evolve_champion.json"
INTERVAL_S = 6 * 3600  # 6 horas
EXECUTE = "--execute" in sys.argv


def log_event(kind, detail):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "kind": kind,
        "detail": detail,
        "mode": "execute" if EXECUTE else "simulate",
    }
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"[{entry['ts'][:19]}] {kind}: {detail}")


def run_evolve():
    if not EXECUTE:
        log_event("WOULD_EVOLVE", "simulacion, no ejecuta evolve_lab.py")
        return
    log_event("EVOLVE_START", "ejecutando core/evolve_lab.py")
    r = subprocess.run(
        [sys.executable, "-u", "-m", "core.evolve_lab"],
        capture_output=True, text=True, timeout=600, cwd=str(ROOT),
    )
    if r.returncode == 0:
        champ_info = "sin champion"
        if CHAMPION.exists():
            try:
                c = json.loads(CHAMPION.read_text())
                champ_info = f"weights={c.get('weights', '?')}"
            except Exception:
                pass
        log_event("EVOLVE_OK", f"evolve_lab completado. {champ_info}")
    else:
        log_event("EVOLVE_FAILED", f"rc={r.returncode} stderr={r.stderr[-200:]}")


def main():
    print("=== TEOS Evolve Runner v1.0 ===")
    print(f"Modo: {'EXECUTE' if EXECUTE else 'SIMULATE'}")
    print(f"Intervalo: {INTERVAL_S//3600}h")
    print(f"Champion output: {CHAMPION}")
    print(f"Log: {LOG}")
    print()
    try:
        while True:
            run_evolve()
            time.sleep(INTERVAL_S)
    except KeyboardInterrupt:
        print("\nEvolve runner detenido.")


if __name__ == "__main__":
    main()
