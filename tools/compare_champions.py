#!/usr/bin/env python3
"""Compara todos los champions (v1 + v2) sobre la misma ventana de evaluacion."""
import json
from pathlib import Path
from statistics import mean, median

ROOT = Path(__file__).resolve().parent.parent
OUTCOMES = ROOT / "data" / "processed" / "learning_outcomes_v2.jsonl"

METHODS = ["adaptativo_neurona","referencia_10m","referencia_1h","media_ultimas_5","ultimo_hashrate"]

def load_champions():
    champs = []
    v1 = ROOT / "data" / "processed" / "evolve_champion.json"
    if v1.exists():
        c = json.loads(v1.read_text())
        champs.append(("v1_original", c.get("weights",{})))
    for p in sorted((ROOT / "data" / "processed").glob("evolve_champion_v2_*.json")):
        c = json.loads(p.read_text())
        name = p.stem.replace("evolve_champion_v2_","")
        champs.append((name, c.get("weights",{})))
    return champs

def main():
    print("Cargando outcomes (ultimos 5000 targets)...")
    by_target = {}
    with OUTCOMES.open() as f:
        for ln in f:
            ln = ln.strip()
            if not ln: continue
            try: o = json.loads(ln)
            except: continue
            t = o.get("target_timestamp")
            if not t: continue
            m = o.get("method")
            pred = o.get("predicted_hashRate_GHs")
            actual = o.get("actual_hashRate_GHs")
            if m and isinstance(pred,(int,float)) and isinstance(actual,(int,float)):
                by_target.setdefault(t,{})[m] = {"pred": float(pred), "actual": float(actual)}
    # Ultimos 5000
    keys = sorted(by_target.keys())[-5000:]
    by_target = {t: by_target[t] for t in keys}
    print(f"Evaluando sobre {len(by_target)} targets recientes\n")

    champs = load_champions()
    if not champs:
        print("No hay champions")
        return

    def eval_champ(weights):
        apes = []
        for t, methods in by_target.items():
            present = [(weights.get(m,0.0), methods[m]["pred"]) for m in methods if weights.get(m,0.0) > 0]
            tw = sum(w for w,_ in present)
            if tw < 1e-9: continue
            pred = sum(w*p for w,p in present) / tw
            actual = None
            for m in METHODS:
                if m in methods: actual = methods[m]["actual"]; break
            if actual is None or actual <= 0: continue
            apes.append(100 * abs(pred - actual) / actual)
        if not apes: return None
        s = sorted(apes)
        return {
            "mean": mean(apes),
            "median": median(apes),
            "p95": s[int(0.95*len(s))],
            "max": s[-1],
            "n": len(apes),
        }

    print(f"{'CHAMPION':<20} {'mean':>8} {'median':>8} {'p95':>8} {'max':>8} {'n':>6}")
    print("-"*70)
    results = []
    for name, w in champs:
        m = eval_champ(w)
        if m:
            print(f"{name:<20} {m['mean']:>7.3f}% {m['median']:>7.3f}% {m['p95']:>7.3f}% {m['max']:>7.2f}% {m['n']:>5}")
            results.append((name, m))
    print()
    if results:
        best = min(results, key=lambda x: x[1]["mean"])
        best_p95 = min(results, key=lambda x: x[1]["p95"])
        print(f"Mejor mean: {best[0]} ({best[1]['mean']:.3f}%)")
        print(f"Mejor p95:  {best_p95[0]} ({best_p95[1]['p95']:.3f}%)")

if __name__ == "__main__":
    main()
