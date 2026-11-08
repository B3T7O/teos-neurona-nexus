"""
TEOS MetaLearner Lite v1
=========================
Shadow-mode selector that recommends the best prediction method
based on recent median APE over a moving window.

This is the Lite version of the full Meta-Learner (Phase 5.5).
It requires < 5 MB of RAM and < 100 ms of CPU per cycle.
It does NOT change the production predictor. It only recommends.

Author: Luis Alberto Siguencia Andrade (B3T7O)
License: Apache 2.0
"""
import json
import statistics
from pathlib import Path
from datetime import datetime, timezone

OUTCOMES = Path("data/processed/learning_outcomes_v2.jsonl")
OUTPUT = Path("data/processed/meta_learner_recommendations.jsonl")
WINDOW_BYTES = 60_000  # read only the last 60 KB
MIN_SAMPLES = 10


def _tail_lines(path: Path, max_bytes: int):
    if not path.exists():
        return []
    try:
        size = path.stat().st_size
        with path.open("rb") as f:
            if size > max_bytes:
                f.seek(size - max_bytes)
                f.readline()  # discard partial line
            data = f.read().decode("utf-8", errors="ignore")
    except OSError:
        return []
    out = []
    for ln in data.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            out.append(json.loads(ln))
        except json.JSONDecodeError:
            pass
    return out


def compute_recommendation():
    records = _tail_lines(OUTCOMES, WINDOW_BYTES)
    by_method = {}
    for r in records:
        method = r.get("method")
        ape = r.get("absolute_percentage_error")
        if not method or not isinstance(ape, (int, float)):
            continue
        by_method.setdefault(method, []).append(ape)

    ranked = []
    for method, apes in by_method.items():
        if len(apes) < MIN_SAMPLES:
            continue
        ranked.append({
            "method": method,
            "n": len(apes),
            "median_ape": round(statistics.median(apes), 4),
            "mean_ape": round(statistics.mean(apes), 4),
        })

    ranked.sort(key=lambda x: x["median_ape"])

    recommendation = {
        "version": "TEOS MetaLearner Lite v1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "window_records": len(records),
        "recommended_method": ranked[0]["method"] if ranked else None,
        "recommended_median_ape": ranked[0]["median_ape"] if ranked else None,
        "ranking": ranked,
        "mode": "shadow",
        "affects_production": False,
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("a", encoding="utf-8") as f:
        f.write(json.dumps(recommendation) + "\n")

    return recommendation


if __name__ == "__main__":
    rec = compute_recommendation()
    print(json.dumps(rec, indent=2, ensure_ascii=False))
