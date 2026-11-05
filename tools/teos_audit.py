#!/usr/bin/env python3
"""
TEOS Audit Engine v0.1
Auditoria de solo lectura de TEOS Neurona Nexus.
No modifica datos. No toca servicios. Solo lee y reporta.

Uso:
    python3 tools/teos_audit.py              # auditoria estandar
    python3 tools/teos_audit.py --full       # incluye chequeo de servicios
    python3 tools/teos_audit.py --json       # solo salida JSON
    python3 tools/teos_audit.py --tail 5000  # solo ultimas N lineas por archivo

Exit codes: 0=sano, 1=advertencia, 2=critico
"""
from __future__ import annotations
import argparse
import json
import subprocess
import sys
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median

ROOT = Path(__file__).resolve().parent.parent
DATA_RAW = ROOT / "data" / "raw"
DATA_PROC = ROOT / "data" / "processed"
AUDIT_DIR = ROOT / "data" / "audit"

LIMITS = {
    "hashRate": (0, 3000), "temp": (0, 90), "vrTemp": (0, 110),
    "frequency": (400, 700), "power": (0, 50),
}
FRESHNESS_MAX = {
    "bitaxe_samples": 300, "bitaxe_control": 3600,
    "learning_outcomes_v2": 3600, "ridge_live_predictions": 3600,
    "analysis_history": 3600,
}
TS_FIELDS = {
    "bitaxe_samples": "timestamp", "bitaxe_control": "timestamp",
    "learning_outcomes_v2": "target_timestamp",
    "ridge_live_predictions": "source_timestamp",
    "analysis_history": "analysis_time",
}
FILES = {
    "bitaxe_samples": DATA_RAW / "bitaxe_samples.jsonl",
    "bitaxe_control": DATA_RAW / "bitaxe_control.jsonl",
    "learning_outcomes_v2": DATA_PROC / "learning_outcomes_v2.jsonl",
    "ridge_live_predictions": DATA_PROC / "ridge_live_predictions.jsonl",
    "analysis_history": DATA_PROC / "analysis_history.jsonl",
}

class R:
    OK, WARN, FAIL = "OK", "WARN", "FAIL"
    def __init__(self, sev, cat, msg, detail=None):
        self.sev, self.cat, self.msg, self.detail = sev, cat, msg, detail
    def to_dict(self):
        d = {"severity": self.sev, "category": self.cat, "message": self.msg}
        if self.detail is not None:
            d["detail"] = self.detail
        return d

def parse_ts(s):
    if not s: return None
    try:
        if s.endswith("Z"): s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s).astimezone(timezone.utc)
    except (ValueError, AttributeError, TypeError):
        return None

def load_jsonl(path, tail=None):
    if not path.exists(): return None, 0
    try:
        with path.open("r", encoding="utf-8") as f:
            lines = list(deque(f, maxlen=tail)) if tail else f.readlines()
    except OSError:
        return None, -1
    recs, errs = [], 0
    for ln in lines:
        ln = ln.strip()
        if not ln: continue
        try: recs.append(json.loads(ln))
        except json.JSONDecodeError: errs += 1
    return recs, errs

def check_file(name, path, tail, results):
    recs, errs = load_jsonl(path, tail)
    if recs is None:
        results.append(R(R.FAIL, "file", f"{name}: no existe o no legible", str(path))); return None
    if errs < 0:
        results.append(R(R.FAIL, "file", f"{name}: error de lectura")); return None
    if not recs:
        results.append(R(R.FAIL, "file", f"{name}: vacio")); return None
    if errs > 0:
        results.append(R(R.WARN, "parse", f"{name}: {errs} lineas no parseables"))
    return recs

def check_freshness(name, recs, field, results):
    ts = [parse_ts(r.get(field)) for r in recs]
    ts = [t for t in ts if t]
    if not ts:
        results.append(R(R.FAIL, "freshness", f"{name}: sin timestamps validos")); return
    age = (datetime.now(timezone.utc) - max(ts)).total_seconds()
    lim = FRESHNESS_MAX.get(name, 3600)
    d = {"age_s": int(age), "latest": max(ts).isoformat()}
    if age > lim * 3: results.append(R(R.FAIL, "freshness", f"{name}: obsoleto ({age:.0f}s > {lim*3}s)", d))
    elif age > lim: results.append(R(R.WARN, "freshness", f"{name}: retraso ({age:.0f}s > {lim}s)", d))
    else: results.append(R(R.OK, "freshness", f"{name}: al dia ({age:.0f}s)", d))

def check_dup(name, recs, field, results):
    seen, dup = set(), 0
    for r in recs:
        v = r.get(field)
        if v is None: continue
        if v in seen: dup += 1
        else: seen.add(v)
    if dup == 0:
        results.append(R(R.OK, "dedup", f"{name}: sin duplicados en {field}"))
    else:
        pct = dup / len(recs) * 100
        sev = R.FAIL if pct > 1 else R.WARN
        results.append(R(sev, "dedup", f"{name}: {dup} duplicados ({pct:.2f}%)", {"field": field}))

def check_ranges(recs, name, results):
    for f, (lo, hi) in LIMITS.items():
        vals = [r.get(f) for r in recs if isinstance(r.get(f), (int, float))]
        if not vals: continue
        out = [v for v in vals if not (lo <= v <= hi)]
        if out:
            results.append(R(R.WARN, "range", f"{name}.{f}: {len(out)}/{len(vals)} fuera de [{lo},{hi}]",
                             {"min": min(out), "max": max(out)}))

def check_quality(outcomes, preds, samples, results):
    apes = [r.get("absolute_percentage_error") for r in outcomes
            if isinstance(r.get("absolute_percentage_error"), (int, float))]
    if apes:
        s = sorted(apes); p95 = s[int(len(s) * 0.95)]
        results.append(R(R.OK, "quality",
            f"APE: mean={mean(apes):.2f}% median={median(apes):.2f}% p95={p95:.2f}%",
            {"n": len(apes), "mean": round(mean(apes), 4), "median": round(median(apes), 4), "p95": round(p95, 4)}))
    if preds and outcomes:
        ratio = len(outcomes) / len(preds) * 100
        sev = R.OK if ratio > 90 else (R.WARN if ratio > 70 else R.FAIL)
        results.append(R(sev, "quality", f"Cobertura eval: {ratio:.1f}% ({len(outcomes)}/{len(preds)})"))
    if samples:
        acc = sum(r.get("sharesAccepted", 0) for r in samples)
        rej = sum(r.get("sharesRejected", 0) for r in samples)
        tot = acc + rej
        if tot > 0:
            p = rej / tot * 100
            sev = R.OK if p < 1 else (R.WARN if p < 5 else R.FAIL)
            results.append(R(sev, "quality", f"Shares rechazados: {p:.2f}% ({rej}/{tot})"))

def check_system(results):
    try:
        out = subprocess.run(["systemctl", "--user", "is-active",
                              "teos-colector", "teos-scheduler", "teos-web"],
                             capture_output=True, text=True, timeout=10)
        states = out.stdout.strip().splitlines()
        for name, st in zip(["teos-colector", "teos-scheduler", "teos-web"], states):
            results.append(R(R.OK if st == "active" else R.FAIL, "system", f"{name}: {st}"))
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        results.append(R(R.WARN, "system", f"systemd no verificable: {e}"))
    try:
        out = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                              "-m", "5", "http://127.0.0.1:8765/"],
                             capture_output=True, text=True, timeout=10)
        code = out.stdout.strip()
        results.append(R(R.OK if code == "200" else R.FAIL, "system",
                         f"web: HTTP {code or 'no responde'}"))
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        results.append(R(R.WARN, "system", f"web no verificable: {e}"))

def print_human(results):
    icons = {R.OK: "OK  ", R.WARN: "WARN", R.FAIL: "FAIL"}
    by_cat = {}
    for r in results: by_cat.setdefault(r.cat, []).append(r)
    for cat in ["file", "parse", "freshness", "dedup", "range", "quality", "system"]:
        if cat not in by_cat: continue
        print(f"\n[{cat.upper()}]")
        for r in by_cat[cat]:
            print(f"  [{icons[r.sev]}] {r.msg}")
            if r.detail: print(f"         {json.dumps(r.detail, ensure_ascii=False)}")
    f = sum(1 for r in results if r.sev == R.FAIL)
    w = sum(1 for r in results if r.sev == R.WARN)
    o = sum(1 for r in results if r.sev == R.OK)
    print("\n" + "=" * 55)
    if f:   print(f"VEREDICTO: CRITICO - {f} fallos, {w} advertencias, {o} OK")
    elif w: print(f"VEREDICTO: ADVERTENCIA - {w} advertencias, {o} OK")
    else:   print(f"VEREDICTO: SANO - {o} chequeos OK")
    print("=" * 55)

def save_report(results):
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    p = AUDIT_DIR / f"audit_{ts}.json"
    summary = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "counts": {s: sum(1 for r in results if r.sev == s) for s in [R.OK, R.WARN, R.FAIL]},
        "results": [r.to_dict() for r in results],
    }
    p.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return p, summary

def main():
    ap = argparse.ArgumentParser(description="TEOS Audit Engine v0.1")
    ap.add_argument("--full", action="store_true", help="incluye chequeo de servicios")
    ap.add_argument("--json", action="store_true", help="solo salida JSON")
    ap.add_argument("--tail", type=int, default=None, help="solo N lineas por archivo")
    ap.add_argument("--no-save", action="store_true", help="no guardar reporte")
    args = ap.parse_args()

    results, data = [], {}
    for name, path in FILES.items():
        data[name] = check_file(name, path, args.tail, results)
    for name, recs in data.items():
        if recs: check_freshness(name, recs, TS_FIELDS[name], results)
    for name in ["ridge_live_predictions", "learning_outcomes_v2"]:
        if data.get(name): check_dup(name, data[name], "prediction_id", results)
    if data.get("bitaxe_samples"): check_ranges(data["bitaxe_samples"], "bitaxe_samples", results)
    check_quality(data.get("learning_outcomes_v2") or [],
                  data.get("ridge_live_predictions") or [],
                  data.get("bitaxe_samples") or [], results)
    if args.full: check_system(results)

    if args.json:
        print(json.dumps([r.to_dict() for r in results], indent=2, ensure_ascii=False))
    else:
        print_human(results)

    if not args.no_save:
        p, s = save_report(results)
        if not args.json:
            print(f"Reporte: {p}")
            print(f"OK={s['counts'][R.OK]}  WARN={s['counts'][R.WARN]}  FAIL={s['counts'][R.FAIL]}")

    sys.exit(2 if any(r.sev == R.FAIL for r in results)
             else (1 if any(r.sev == R.WARN for r in results) else 0))

if __name__ == "__main__":
    main()
