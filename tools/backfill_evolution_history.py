#!/usr/bin/env python3
"""Rellena el historial central con evoluciones ya existentes."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.evolution_history import record


def main():
    # 1. Del champion actual
    champ = ROOT / "data" / "processed" / "evolve_champion.json"
    if champ.exists():
        try:
            c = json.loads(champ.read_text())
            record(
                "evolve_lab", "champion_update",
                f"champion del {c.get('timestamp', '?')[:19]}",
                extra={
                    "ape_mean": c.get("ape_mean"),
                    "weights": c.get("weights"),
                    "targets_evaluated": c.get("targets_evaluated"),
                },
            )
            print("OK: champion actual registrado")
        except Exception as e:
            print(f"ERROR champion: {e}")

    # 2. Del log de evolve
    log = ROOT / "data" / "evolve" / "evolve_log.jsonl"
    if log.exists():
        n = 0
        for ln in log.open():
            try:
                o = json.loads(ln)
            except Exception:
                continue
            kind = o.get("kind")
            if kind in ("EVOLVE_OK", "EVOLVE_FAILED"):
                record(
                    "evolve_lab",
                    "ok" if kind == "EVOLVE_OK" else "failed",
                    o.get("detail", "")[:80],
                )
                n += 1
        print(f"OK: {n} eventos del log registrados")


if __name__ == "__main__":
    main()
