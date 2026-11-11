#!/usr/bin/env python3
"""
Filtra samples fisicamente invalidos del Bitaxe.
Un sample es invalido si hashRate no es consistente con frequency/power.
Crea bitaxe_samples.clean.jsonl (NO sobreescribe el original).
"""
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "bitaxe_samples.marked.jsonl"
CLEAN = ROOT / "data" / "raw" / "bitaxe_samples.clean.jsonl"

HR_MIN_PER_MHZ = 0.5
HR_MAX_PER_MHZ = 5.0


def is_valid(o):
    hr = o.get("hashRate") or o.get("hashRate_1m")
    pw = o.get("power")
    fr = o.get("frequency")
    if hr is None or pw is None or fr is None:
        return True  # sin datos para validar -> conservar
    if fr <= 0 or hr < 0 or pw < 0:
        return False
    return (fr * HR_MIN_PER_MHZ) <= hr <= (fr * HR_MAX_PER_MHZ)


def main():
    # Backup una sola vez
    bak = RAW.with_suffix(".jsonl.bak")
    if not bak.exists():
        shutil.copy2(RAW, bak)
        print(f"backup creado: {bak.name}", flush=True)

    total = kept = 0
    bad_samples = []
    with RAW.open("r", encoding="utf-8", errors="ignore") as f, \
         CLEAN.open("w", encoding="utf-8") as out:
        for ln in f:
            ln = ln.rstrip("\n")
            if not ln.strip():
                continue
            total += 1
            try:
                o = json.loads(ln)
            except Exception:
                out.write(ln + "\n")
                kept += 1
                continue
            if is_valid(o):
                out.write(ln + "\n")
                kept += 1
            else:
                bad_samples.append(o)

    print(f"total={total}  kept={kept}  removed={total - kept}", flush=True)
    if bad_samples:
        print("\nmuestra de invalidos removidos:", flush=True)
        for o in bad_samples[:10]:
            print(f"  ts={o.get('timestamp')}  hr={o.get('hashRate')}  "
                  f"fr={o.get('frequency')}  pw={o.get('power')}", flush=True)
    print(f"\narchivo limpio: {CLEAN}", flush=True)


if __name__ == "__main__":
    main()
