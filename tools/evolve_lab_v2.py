#!/usr/bin/env python3
"""
Evolve Lab v2 - GA con 3 modos de fitness.
Modos: multi_objective | temporal | regime_low | regime_high
Uso: python3 -u tools/evolve_lab_v2.py --mode multi_objective
"""
import json, sys, random, argparse
from pathlib import Path
from statistics import mean, median
from datetime import datetime, timezone, timedelta
from bisect import bisect_left

ROOT = Path(__file__).resolve().parent.parent
OUTCOMES = ROOT / "data" / "processed" / "learning_outcomes_v2.jsonl"
SAMPLES = ROOT / "data" / "raw" / "bitaxe_samples.marked.jsonl"
OUT_DIR = ROOT / "data" / "processed"

METHODS = ["adaptativo_neurona", "referencia_10m", "referencia_1h",
           "media_ultimas_5", "ultimo_hashrate"]

POPULATION = 60
GENERATIONS = 40
SURVIVORS = 15
MUTATION_RATE = 0.15
MUTATION_MAGNITUDE = 0.12
MAX_TARGETS = 25000

def parse_ts(s):
    if not s: return None
    try:
        if s.endswith("Z"): s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except: return None

def load_outcomes(since_days=None):
    cutoff = None
    if since_days:
        cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)
    by_target = {}
    with OUTCOMES.open() as f:
        for ln in f:
            ln = ln.strip()
            if not ln: continue
            try: o = json.loads(ln)
            except: continue
            t = o.get("target_timestamp")
            if not t: continue
            if cutoff:
                dt = parse_ts(t)
                if dt is None or dt < cutoff: continue
            m = o.get("method")
            pred = o.get("predicted_hashRate_GHs")
            actual = o.get("actual_hashRate_GHs")
            if m and isinstance(pred,(int,float)) and isinstance(actual,(int,float)):
                by_target.setdefault(t, {})[m] = {"pred": float(pred), "actual": float(actual)}
    # Limitar a los ultimos MAX_TARGETS
    if len(by_target) > MAX_TARGETS:
        keep = set(sorted(by_target.keys())[-MAX_TARGETS:])
        by_target = {t: by_target[t] for t in keep}
    return by_target

def weighted_pred(weights, methods):
    present = [(weights.get(m,0.0), methods[m]["pred"]) for m in methods if weights.get(m,0.0) > 0]
    tw = sum(w for w,_ in present)
    if tw < 1e-9: return None
    return sum(w*p for w,p in present) / tw

def get_actual(methods):
    for m in METHODS:
        if m in methods:
            return methods[m]["actual"]
    return None

def compute_apes(weights, outcomes):
    apes = []
    for t, methods in outcomes.items():
        pred = weighted_pred(weights, methods)
        if pred is None: continue
        actual = get_actual(methods)
        if actual is None or actual <= 0: continue
        apes.append(100 * abs(pred - actual) / actual)
    return apes

def percentile(values, p):
    if not values: return 0
    s = sorted(values)
    return s[min(len(s)-1, int(p/100 * len(s)))]

def fitness_mean(w, o):
    apes = compute_apes(w, o)
    return mean(apes) if apes else float('inf')

def fitness_multi(w, o):
    apes = compute_apes(w, o)
    if not apes: return float('inf')
    return 0.6*mean(apes) + 0.4*percentile(apes, 95)

def random_weights():
    w = [random.random() for _ in METHODS]
    t = sum(w)
    return {m: w[i]/t for i, m in enumerate(METHODS)}

def mutate(w):
    new = dict(w)
    for m in new:
        if random.random() < MUTATION_RATE:
            new[m] += random.uniform(-MUTATION_MAGNITUDE, MUTATION_MAGNITUDE)
            new[m] = max(0, new[m])
    t = sum(new.values())
    if t < 1e-9: return random_weights()
    return {m: v/t for m,v in new.items()}

def crossover(w1, w2):
    c = {}
    for m in w1:
        a = random.random()
        c[m] = a*w1[m] + (1-a)*w2[m]
    t = sum(c.values())
    return {m: v/t for m,v in c.items()}

def genetic_algorithm(fitness_fn, outcomes, seed=42):
    random.seed(seed)
    pop = [random_weights() for _ in range(POPULATION)]
    best_overall = None
    best_fit = float('inf')
    for gen in range(GENERATIONS):
        scored = [(fitness_fn(w, outcomes), w) for w in pop]
        scored.sort(key=lambda x: x[0])
        if scored[0][0] < best_fit:
            best_fit = scored[0][0]
            best_overall = scored[0][1]
        survivors = [w for _,w in scored[:SURVIVORS]]
        new_pop = survivors[:2]
        while len(new_pop) < POPULATION:
            p1 = random.choice(survivors); p2 = random.choice(survivors)
            new_pop.append(mutate(crossover(p1, p2)))
        pop = new_pop
        if gen % 10 == 0:
            print(f"  Gen {gen}: best_fit={best_fit:.4f}", flush=True)
    return best_overall, best_fit

def compute_regime_labels(outcomes):
    print("  Calculando regimenes de volatilidad...", flush=True)
    samples = []
    with SAMPLES.open() as f:
        for ln in f:
            ln = ln.strip()
            if not ln: continue
            try: o = json.loads(ln)
            except: continue
            if o.get("quality") != "ok": continue
            hr = o.get("hashRate")
            ts = parse_ts(o.get("timestamp"))
            if ts and isinstance(hr,(int,float)) and hr > 0:
                samples.append({"dt": ts, "hr": float(hr)})
    samples.sort(key=lambda x: x["dt"])
    dts = [s["dt"] for s in samples]
    hrs = [s["hr"] for s in samples]
    labels = {}
    stds = []
    for t in outcomes:
        tdt = parse_ts(t)
        if tdt is None: continue
        idx = bisect_left(dts, tdt)
        if idx < 20: continue
        window = hrs[max(0,idx-20):idx]
        if len(window) < 10: continue
        m = mean(window)
        var = sum((x-m)**2 for x in window) / len(window)
        std = var ** 0.5
        stds.append(std); labels[t] = std
    if not stds: return None
    threshold = median(stds)
    return {t: ("high_vol" if std > threshold else "low_vol") for t, std in labels.items()}

def save_champion(name, mode, weights, fitness_val, outcomes):
    apes = compute_apes(weights, outcomes)
    if not apes:
        print(f"  Sin APEs, no se guarda {name}")
        return
    champ = {
        "version": "TEOS Evolve Lab v2.0",
        "mode": mode,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "weights": {m: round(w, 4) for m,w in weights.items()},
        "fitness_value": round(fitness_val, 4),
        "metrics": {
            "ape_mean": round(mean(apes), 4),
            "ape_median": round(median(apes), 4),
            "ape_p95": round(percentile(apes, 95), 4),
            "ape_max": round(max(apes), 4),
            "n": len(apes),
        }
    }
    out = OUT_DIR / f"evolve_champion_v2_{name}.json"
    out.write_text(json.dumps(champ, indent=2))
    print(f"  OK: {out.name}")
    print(f"    mean={champ['metrics']['ape_mean']}% p95={champ['metrics']['ape_p95']}% n={champ['metrics']['n']}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True, choices=["multi_objective","temporal","regime_low","regime_high"])
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()
    print(f"=== MODE: {args.mode} ===")
    if args.mode == "temporal":
        o = load_outcomes(since_days=args.days)
        print(f"Outcomes (last {args.days}d): {len(o)}")
        w, f = genetic_algorithm(fitness_mean, o)
        save_champion("temporal", args.mode, w, f, o)
    elif args.mode == "multi_objective":
        o = load_outcomes()
        print(f"Outcomes (all): {len(o)}")
        w, f = genetic_algorithm(fitness_multi, o)
        save_champion("multi_obj", args.mode, w, f, o)
    elif args.mode in ("regime_low","regime_high"):
        o = load_outcomes()
        labels = compute_regime_labels(o)
        if not labels: print("Sin labels"); return
        tl = "low_vol" if args.mode=="regime_low" else "high_vol"
        subset = {t: o[t] for t in o if labels.get(t) == tl}
        print(f"Outcomes ({tl}): {len(subset)}")
        w, f = genetic_algorithm(fitness_mean, subset)
        save_champion(args.mode, args.mode, w, f, subset)

if __name__ == "__main__":
    main()
