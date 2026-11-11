"""
TEOS Best Share Tracker
=======================
Tracks bestDiff history: detects new records, stores top shares,
and provides data for the dashboard panel.
"""
import json
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "data" / "raw" / "bitaxe_samples.marked.jsonl"
STATE = ROOT / "data" / "processed" / "bestshare_state.json"


def _load_recent(n=200):
    if not SAMPLES.exists():
        return []
    with SAMPLES.open("rb") as f:
        size = SAMPLES.stat().st_size
        f.seek(max(0, size - 80000))
        data = f.read().decode("utf-8", errors="ignore")
    out = []
    for ln in data.splitlines()[-n:]:
        ln = ln.strip()
        if not ln: continue
        try:
            r = json.loads(ln)
            if isinstance(r.get("bestDiff"), (int, float)):
                out.append({
                    "ts": r.get("timestamp", ""),
                    "bestDiff": r["bestDiff"],
                })
        except json.JSONDecodeError:
            pass
    return out


def update_and_get():
    """Actualiza el estado y devuelve el resumen actual."""
    recent = _load_recent()
    if not recent:
        return {"error": "Sin datos"}

    prev_state = {}
    if STATE.exists():
        try:
            prev_state = json.loads(STATE.read_text())
        except Exception:
            prev_state = {}

    current_best = recent[-1]["bestDiff"]
    previous_best = prev_state.get("current_best", 0)

    is_new_record = current_best > previous_best and current_best > 0

    # Histórico de los top 5
    top_history = prev_state.get("top_history", [])
    if is_new_record:
        top_history.append({
            "bestDiff": current_best,
            "ts": recent[-1]["ts"],
            "detected_at": datetime.now(timezone.utc).isoformat(),
        })
        top_history = sorted(top_history, key=lambda x: x["bestDiff"], reverse=True)[:5]

    # Contador de records (cuántas veces subió)
    record_count = prev_state.get("record_count", 0) + (1 if is_new_record else 0)

    new_state = {
        "current_best": current_best,
        "previous_best": previous_best,
        "is_new_record": is_new_record,
        "record_count": record_count,
        "top_history": top_history,
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "last_best_ts": recent[-1]["ts"],
    }
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(new_state, indent=2), encoding="utf-8")
    return new_state


if __name__ == "__main__":
    print(json.dumps(update_and_get(), indent=2, ensure_ascii=False))
