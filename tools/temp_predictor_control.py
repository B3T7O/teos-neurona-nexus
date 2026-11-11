#!/usr/bin/env python3
"""
Paso 3 (Opcion D): predictor de temperatura + simulacion de control predictivo.
"""
import json
import math
from pathlib import Path
from datetime import datetime, timezone
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "data" / "raw" / "bitaxe_samples.marked.jsonl"
TEMP_THRESHOLD = 65.0  # umbral de alerta termica


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
    print("Cargando samples...")
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
            temp = safe(o.get("temp"))
            if dt is None or not math.isfinite(temp):
                continue
            samples.append({
                "_dt": dt,
                "ts": o.get("timestamp"),
                "temp": temp,
                "vrTemp": safe(o.get("vrTemp")),
                "power": safe(o.get("power")),
                "voltage": safe(o.get("voltage")),
                "frequency": safe(o.get("frequency")),
                "hashRate": safe(o.get("hashRate")),
            })
    samples.sort(key=lambda x: x["_dt"])
    print(f"Samples: {len(samples)}")
    if len(samples) < 500:
        print("Pocos samples.")
        return

    # Construir filas (features en t, target temp en t+1)
    rows = []
    for i in range(10, len(samples) - 1):
        s, t = samples[i], samples[i + 1]
        if (t["_dt"] - s["_dt"]).total_seconds() > 300:
            continue
        if not all(math.isfinite(s[k]) for k in
                   ["temp", "vrTemp", "power", "voltage", "frequency"]):
            continue

        t_now = s["temp"]
        t_prev5 = samples[i - 5]["temp"]
        t_prev10 = samples[i - 10]["temp"]
        delta5 = t_now - t_prev5
        delta10 = t_now - t_prev10
        hour = s["_dt"].hour
        dow = s["_dt"].weekday()

        feats = {
            "temp_now": t_now,
            "delta5": delta5,
            "delta10": delta10,
            "vrTemp": s["vrTemp"],
            "power": s["power"],
            "voltage": s["voltage"],
            "frequency": s["frequency"],
            "hashRate": s["hashRate"],
            "hour_sin": math.sin(2 * math.pi * hour / 24),
            "hour_cos": math.cos(2 * math.pi * hour / 24),
            "dow_sin": math.sin(2 * math.pi * dow / 7),
            "dow_cos": math.cos(2 * math.pi * dow / 7),
        }
        if not all(math.isfinite(v) for v in feats.values()):
            continue
        rows.append({
            "ts": t["ts"],
            "feats": feats,
            "target_temp": t["temp"],
            "baseline_temp": t_now,
            "temp_now": t_now,
        })

    print(f"Filas dataset: {len(rows)}")
    if len(rows) < 500:
        print("Pocas filas.")
        return

    split = int(len(rows) * 0.7)
    train, test = rows[:split], rows[split:]
    print(f"Train: {len(train)} | Test: {len(test)}")

    names = list(train[0]["feats"].keys())
    X_tr = np.array([[r["feats"][k] for k in names] for r in train])
    y_tr = np.array([r["target_temp"] for r in train])
    X_te = np.array([[r["feats"][k] for k in names] for r in test])
    y_te = np.array([r["target_temp"] for r in test])
    y_base = np.array([r["baseline_temp"] for r in test])

    mu, sigma, w, y_mean = ridge_fit(X_tr, y_tr, alpha=1.0)
    y_pred = ridge_predict(X_te, mu, sigma, w, y_mean)

    def report(y_hat, name):
        mae = float(np.mean(np.abs(y_te - y_hat)))
        p95 = float(np.percentile(np.abs(y_te - y_hat), 95))
        print(f"{name:20s} MAE={mae:6.3f}°C  p95={p95:6.3f}°C")
        return mae, p95

    print("\n=== Prediccion de temperatura (test) ===")
    b_mae, b_p95 = report(y_base, "baseline (copia)")
    m_mae, m_p95 = report(y_pred, "modelo_ridge")
    print(f"\nΔ MAE: {b_mae - m_mae:+.3f}°C   Δ p95: {b_p95 - m_p95:+.3f}°C")

    if m_mae < b_mae - 0.01:
        print("✅ El modelo predice mejor que 'copia'. Usar para control predictivo.")
    else:
        print("⚠️  'Copia' ya es optimo (inercia termica domina). Control predictivo con modelo")
        print("   solo sirve si el margen contra umbral es pequeno.")

    # ==== Simulacion de control ====
    print("\n=== Simulacion de control termico ===")
    print(f"Umbral: temp > {TEMP_THRESHOLD}°C")

    # Reactivo: usa temp actual
    reactivo_alerts = sum(1 for r in test if r["temp_now"] > TEMP_THRESHOLD)
    # Predictivo: usa temp predicha
    pred_alerts = sum(1 for z in y_pred if z > TEMP_THRESHOLD)

    print(f"\n  Reactivo  (actua si temp(t) > {TEMP_THRESHOLD}): {reactivo_alerts} alertas")
    print(f"  Predictivo (actua si temp_pred(t+1) > {TEMP_THRESHOLD}): {pred_alerts} alertas")

    # Cuantas veces el predictivo se adelanta a una alerta reactiva
    adelantos = 0
    for i in range(len(test) - 1):
        if y_pred[i] > TEMP_THRESHOLD and test[i]["temp_now"] <= TEMP_THRESHOLD:
            # Predijo alerta pero aun no era real -> se adelanto
            if i + 1 < len(test) and test[i + 1]["temp_now"] > TEMP_THRESHOLD:
                adelantos += 1
    print(f"\n  Anticipaciones correctas (pred > umbral, siguiente real > umbral): {adelantos}")

    # Comparar margenes
    if len(y_pred) > 0:
        margen_modelo = float(np.mean(y_pred - y_te))
        margen_base = float(np.mean(y_base - y_te))
        print(f"\n  Sesgo modelo: {margen_modelo:+.3f}°C")
        print(f"  Sesgo baseline: {margen_base:+.3f}°C")

    # Importancia
    print("\n=== Coef estandarizado (top 5) ===")
    for name, c in sorted(zip(names, w), key=lambda x: abs(x[1]), reverse=True)[:5]:
        print(f"  {name:15s} {c:+8.3f}")

    # Guardar modelo
    model_path = ROOT / "data" / "processed" / "temp_model.json"
    model_path.write_text(json.dumps({
        "features": names,
        "mu": mu.tolist(),
        "sigma": sigma.tolist(),
        "w": w.tolist(),
        "y_mean": y_mean,
        "mae_test": m_mae,
        "baseline_mae": b_mae,
    }, indent=2))
    print(f"\nModelo guardado: {model_path}")


if __name__ == "__main__":
    main()
