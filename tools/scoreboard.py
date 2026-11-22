#!/usr/bin/env python3
# TEOS - Tablero de evaluacion v0 (solo lectura).
# Compara cada metodo con referencia_10m sobre las MISMAS muestras, excluyendo anomalias.
import json, random, statistics as st
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTCOMES = ROOT / "data/processed/learning_outcomes_v2.jsonl"
LEDGER = ROOT / "data/processed/anomaly_events.jsonl"
OUT = ROOT / "data/processed/scoreboard.json"
BASE = "referencia_10m"
SKIP_METHODS = {"mlp_lite"}  # en cuarentena
DAYS = 14


def tsd(v):
    return datetime.fromisoformat(v.replace("Z", "+00:00"))


def anomaly_times():
    s = set()
    if LEDGER.exists():
        with LEDGER.open(encoding="utf-8") as f:
            for line in f:
                try:
                    s.add(tsd(json.loads(line)["timestamp"]))
                except Exception:
                    pass
    return s


def verdict(ci_lo, ci_hi):
    if ci_hi < 0:
        return "MEJOR"
    if ci_lo > 0:
        return "PEOR"
    return "EMPATE"


def load(now, anomalies):
    cutoff = now - timedelta(days=DAYS)
    rows, skipped, total = {}, 0, 0
    with OUTCOMES.open(encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
                m = r["method"]
                if m in SKIP_METHODS:
                    continue
                src = tsd(r["source_timestamp"])
                tgt = tsd(r["target_timestamp"])
                if src < cutoff:
                    continue
                a = float(r["actual_hashRate_GHs"])
                p = float(r["predicted_hashRate_GHs"])
                if a <= 0:
                    continue
            except Exception:
                continue
            total += 1
            if src in anomalies or tgt in anomalies:
                skipped += 1
                continue
            rows.setdefault(src, {})[m] = abs(a - p) / a * 100
    return rows, total, skipped


def compare(rows, t_lo, t_hi, method):
    diffs, apes, bases = [], [], []
    for src, v in rows.items():
        if t_lo <= src < t_hi and method in v and BASE in v:
            diffs.append(v[method] - v[BASE])
            apes.append(v[method])
            bases.append(v[BASE])
    n = len(diffs)
    if n < 50:
        return None
    rnd = random.Random(0)
    boots = sorted(st.fmean(rnd.choices(diffs, k=n)) for _ in range(1000))
    ci_lo, ci_hi = boots[25], boots[974]
    return {
        "n": n,
        "med_ape": round(st.median(apes), 3),
        "med_ref": round(st.median(bases), 3),
        "mean_diff_pts": round(st.fmean(diffs), 4),
        "ci95": [round(ci_lo, 4), round(ci_hi, 4)],
        "wins_pct": round(100 * sum(1 for d in diffs if d < 0) / n, 1),
        "verdict": verdict(ci_lo, ci_hi),
    }


def main():
    now = datetime.now(timezone.utc)
    anomalies = anomaly_times()
    rows, total, skipped = load(now, anomalies)
    methods = sorted({m for v in rows.values() for m in v} - {BASE})
    periods = [
        ("ultimos 7 dias", now - timedelta(days=7), now + timedelta(days=1)),
        ("7 dias anteriores", now - timedelta(days=14), now - timedelta(days=7)),
    ]
    report = {"generated_at": now.isoformat(), "baseline": BASE,
              "anomaly_events_excluded": len(anomalies),
              "rows_read": total, "rows_skipped_anomaly": skipped, "periods": {}}
    print(f"filas leidas: {total} | excluidas por anomalia: {skipped} | rival: {BASE} (dif<0 = mejor que el rival)")
    for label, t_lo, t_hi in periods:
        print(f"\n--- {label} ---")
        print(f"{'metodo':20}{'n':>6}{'medAPE':>8}{'medRef':>8}{'dif_media':>10}{'IC95%':>20}{'gana%':>7}  veredicto")
        report["periods"][label] = {}
        for m in methods:
            c = compare(rows, t_lo, t_hi, m)
            if not c:
                continue
            report["periods"][label][m] = c
            print(f"{m:20}{c['n']:6d}{c['med_ape']:8.3f}{c['med_ref']:8.3f}{c['mean_diff_pts']:10.4f}"
                  f"{str(c['ci95']):>20}{c['wins_pct']:7.1f}  {c['verdict']}")
    OUT.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"\nguardado en {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
