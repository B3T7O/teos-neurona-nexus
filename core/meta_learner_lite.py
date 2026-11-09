"""
TEOS MetaLearner Lite v1 (Panoramic)
====================================
Multi-window selector: looks at 5 time windows (1h, 6h, 12h, 18h, 24h).
If windows disagree, the method with the best combined median APE wins.
Does NOT affect production.
"""
import json
import statistics
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter

OUTCOMES = Path("data/processed/learning_outcomes_v2.jsonl")
OUTPUT = Path("data/processed/meta_learner_recommendations.jsonl")

WINDOWS = [
    ("1h", 30_000),
    ("6h", 180_000),
    ("12h", 360_000),
    ("18h", 540_000),
    ("24h", 720_000),
]
MIN_SAMPLES = 10

def _tail_lines(path, max_bytes):
    if not path.exists(): return []
    try:
        size = path.stat().st_size
        with path.open("rb") as f:
            if size > max_bytes:
                f.seek(size - max_bytes)
                f.readline()
            data = f.read().decode("utf-8", errors="ignore")
    except OSError: return []
    out = []
    for ln in data.splitlines():
        ln = ln.strip()
        if not ln: continue
        try: out.append(json.loads(ln))
        except json.JSONDecodeError: pass
    return out

def _window_analysis(records):
    by_method = {}
    for r in records:
        m = r.get("method")
        ape = r.get("absolute_percentage_error")
        if m and isinstance(ape, (int, float)):
            by_method.setdefault(m, []).append(ape)
    stats = {}
    for m, apes in by_method.items():
        if len(apes) >= MIN_SAMPLES:
            stats[m] = {
                "n": len(apes),
                "median_ape": round(statistics.median(apes), 4),
                "mean_ape": round(statistics.mean(apes), 4),
            }
    winner = min(stats, key=lambda x: stats[x]["median_ape"]) if stats else None
    return stats, winner

def compute_recommendation():
    window_winners = {}
    all_method_apes = {}

    for name, size in WINDOWS:
        records = _tail_lines(OUTCOMES, size)
        stats, winner = _window_analysis(records)
        window_winners[name] = winner
        for m, s in stats.items():
            all_method_apes.setdefault(m, []).append(s["median_ape"])

    valid = [w for w in window_winners.values() if w]
    if valid:
        counts = Counter(valid)
        top_method, top_count = counts.most_common(1)[0]
    else:
        top_method, top_count = None, 0

    combined = {}
    for m, apes in all_method_apes.items():
        combined[m] = {
            "combined_median_ape": round(statistics.mean(apes), 4),
            "windows_present": len(apes),
        }

    # Consenso >= 3 ventanas -> gana el consenso
    # Si discrepan -> gana el de menor APE combinado
    if top_count >= 3:
        recommended = top_method
        confidence = "ALTA" if top_count == 5 else "MEDIA"
    else:
        if combined:
            recommended = min(combined, key=lambda x: combined[x]["combined_median_ape"])
            confidence = "BAJA"
        else:
            recommended, confidence = None, "NULA"

    ranking = []
    for m in sorted(combined, key=lambda x: combined[x]["combined_median_ape"]):
        ranking.append({
            "method": m,
            "combined_median_ape": combined[m]["combined_median_ape"],
            "windows_present": combined[m]["windows_present"],
        })

    rec = {
        "version": "TEOS MetaLearner Lite v1 (Panoramic)",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "recommended_method": recommended,
        "confidence": confidence,
        "window_winners": window_winners,
        "window_agreement": f"{top_count}/5",
        "ranking": ranking,
        "mode": "shadow",
        "affects_production": False,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    return rec

if __name__ == "__main__":
    print(json.dumps(compute_recommendation(), indent=2, ensure_ascii=False))
