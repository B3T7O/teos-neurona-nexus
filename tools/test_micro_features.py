#!/usr/bin/env python3
"""
v2: ridge CON intercepto (centrando y). Compara contra h1h y h1m como baselines.
"""
import json
import math
from pathlib import Path
from datetime import datetime, timezone
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "data" / "raw" / "bitaxe_samples.marked.jsonl"


def parse_ts(s):
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def safe(x):
    if isinstance(x, (int, float)) and math.isfinite(x):
        return float(x)
    return float("nan")


def ridge_fit(X, y, alpha=1.0):
    mu = X.mean(axis=0)
    sigma = X.std(axis=0) + 1e-8
    y_mean = float(y.mean())
    Xs = (X - mu) / sigma
    w = np.linalg.solve(Xs.T @ Xs + alpha * np.eye(Xs.shape[1]), Xs.T @ (y - y_mean))
    return mu, sigma, w, y_mean


def ridge_predict(X, mu, sigma, w, y_mean):
    return ((X - mu) / sigma) @ w + y_mean


def main():
    samples = []
    with SAMPLES.open("r", encoding="utf-8", errors="ignore") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                o = json.loads(ln)
            except Exception:
                continue
            if o.get("quality") != "ok":
                continue
            dt = parse_ts(o.get("timestamp"))
            hr = o.get("hashRate")
            if dt is None or not isinstance(hr, (int, float)) or hr <= 0:
                continue
            samples.append({
                "dt": dt, "hashRate": hr,
                "h1m": safe(o.get("hashRate_1m")),
                "h10m": safe(o.get("hashRate_10m")),
                "h1h": safe(o.get("hashRate_1h")),
                "temp": safe(o.get("temp")),
                "vrTemp": safe(o.get("vrTemp")),
                "power": safe(o.get("power")),
                "freq": safe(o.get("frequency")),
                "current": safe(o.get("current")),
            })
    samples.sort(key=lambda x: x["dt"])
    print(f"Samples (quality=ok): {len(samples)}")

    rows = []
    for i in range(20, len(samples) - 1):
        s, t = samples[i], samples[i + 1]
        if (t["dt"] - s["dt"]).total_seconds() > 300:
            continue
        if not all(math.isfinite(x) and x > 0 for x in [s["h1m"], s["h10m"], s["h1h"]]):
            continue

        h5 = [samples[j]["hashRate"] for j in range(i - 5, i)]
        h10 = [samples[j]["hashRate"] for j in range(i - 10, i)]
        h20 = [samples[j]["hashRate"] for j in range(i - 20, i)]
        momentum = (s["h1m"] - s["h10m"]) / s["h10m"]
        ratio = s["h1m"] / s["h1h"]
        temp_prev = safe(samples[i - 10]["temp"])
        temp_delta = (s["temp"] - temp_prev) if (math.isfinite(s["temp"]) and math.isfinite(temp_prev)) else 0.0
        hour, dow = s["dt"].hour, s["dt"].weekday()

        feats = {
            "h1m": s["h1m"], "h10m": s["h10m"], "h1h": s["h1h"],
            "std5": float(np.std(h5)), "std10": float(np.std(h10)), "std20": float(np.std(h20)),
            "momentum": momentum, "ratio": ratio,
            "temp": s["temp"], "vrTemp": s["vrTemp"],
            "power": s["power"], "freq": s["freq"], "current": s["current"],
            "temp_delta": temp_delta,
            "hour_sin": math.sin(2*math.pi*hour/24), "hour_cos": math.cos(2*math.pi*hour/24),
            "dow_sin": math.sin(2*math.pi*dow/7), "dow_cos": math.cos(2*math.pi*dow/7),
        }
        if not all(math.isfinite(v) for v in feats.values()):
            continue
        rows.append({"feats": feats, "target": t["hashRate"],
                     "baseline_h1h": s["h1h"], "baseline_h1m": s["h1m"]})

    print(f"Filas dataset: {len(rows)}")
    if len(rows) < 1000:
        print("Pocas filas.")
        return

    split = int(len(rows) * 0.7)
    train, test = rows[:split], rows[split:]
    print(f"Train: {len(train)} | Test: {len(test)}")

    names = list(train[0]["feats"].keys())
    X_train = np.array([[r["feats"][k] for k in names] for r in train])
    y_train = np.array([r["target"] for r in train])
    X_test = np.array([[r["feats"][k] for k in names] for r in test])
    y_test = np.array([r["target"] for r in test])
    y_h1h = np.array([r["baseline_h1h"] for r in test])
    y_h1m = np.array([r["baseline_h1m"] for r in test])

    mu, sigma, w, y_mean = ridge_fit(X_train, y_train, alpha=1.0)
    y_pred = np.clip(ridge_predict(X_test, mu, sigma, w, y_mean), 1.0, None)

    def report(y_hat, name):
        mae = float(np.mean(np.abs(y_test - y_hat)))
        ape = 100 * np.abs(y_test - y_hat) / np.clip(y_test, 1.0, None)
        print(f"{name:15s} MAE={mae:7.1f}  APE mean={ape.mean():6.2f}%  "
              f"median={np.median(ape):6.2f}%  p95={np.percentile(ape, 95):6.2f}%")
        return float(ape.mean()), float(np.percentile(ape, 95))

    print("\n=== Resultados (test) ===")
    b1_mean, b1_p95 = report(y_h1h, "h1h (baseline)")
    b2_mean, b2_p95 = report(y_h1m, "h1m")
    m_mean, m_p95 = report(y_pred, "modelo_ridge")

    print(f"\nΔ vs h1h:  mean {b1_mean - m_mean:+.3f} pp | p95 {b1_p95 - m_p95:+.3f} pp")
    print(f"Δ vs h1m:  mean {b2_mean - m_mean:+.3f} pp | p95 {b2_p95 - m_p95:+.3f} pp")

    best_base = min(b1_mean, b2_mean)
    if m_mean < best_base - 0.1:
        print("✅ El modelo bate al mejor baseline. Integrar.")
    elif m_mean > best_base + 0.1:
        print("❌ El modelo pierde contra baselines. Descartar estas features.")
    else:
        print("⚠️  Sin mejora clara. Revisar features individuales.")

    print("\n=== Importancia (coef estandarizado, top 10) ===")
    for name, c in sorted(zip(names, w), key=lambda x: abs(x[1]), reverse=True)[:10]:
        print(f"  {name:15s} {c:+10.3f}")


if __name__ == "__main__":
    main()
