#!/usr/bin/env python3
"""
Marca cada sample con 'quality' sin borrar nada.
  ok | corrupt_spike | idle | bad_zero
Salida: data/raw/bitaxe_samples.marked.jsonl
"""
import json, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "bitaxe_samples.jsonl"
MARKED = ROOT / "data" / "raw" / "bitaxe_samples.marked.jsonl"

HR_MIN_PER_MHZ = 0.5
HR_MAX_PER_MHZ = 5.0
IDLE_THRESHOLD = 50.0

def classify(o):
    hr = o.get("hashRate")
    if hr is None: hr = o.get("hashRate_1m")
    pw = o.get("power"); fr = o.get("frequency")
    if hr is None or pw is None or fr is None: return "ok"
    if pw <= 0.5 or fr <= 0: return "bad_zero"
    if hr < IDLE_THRESHOLD: return "idle"
    if hr < fr * HR_MIN_PER_MHZ or hr > fr * HR_MAX_PER_MHZ: return "corrupt_spike"
    return "ok"

def main():
    bak = RAW.with_suffix(".jsonl.bak")
    if not bak.exists():
        shutil.copy2(RAW, bak)
        print(f"backup: {bak.name}", flush=True)
    counts = {"ok":0,"corrupt_spike":0,"idle":0,"bad_zero":0}
    total = 0
    with RAW.open("r", encoding="utf-8", errors="ignore") as f, MARKED.open("w", encoding="utf-8") as out:
        for ln in f:
            ln = ln.rstrip("\n")
            if not ln.strip(): continue
            total += 1
            try: o = json.loads(ln)
            except Exception:
                out.write(ln + "\n"); continue
            q = classify(o); o["quality"] = q; counts[q] += 1
            out.write(json.dumps(o, ensure_ascii=False) + "\n")
    print(f"\ntotal={total}", flush=True)
    for k,v in counts.items(): print(f"  {k:15s} {v}", flush=True)
    print(f"\nsalida: {MARKED}", flush=True)

if __name__ == "__main__":
    main()
