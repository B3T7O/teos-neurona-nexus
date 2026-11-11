#!/usr/bin/env python3
"""
Paso 2 (Opcion C): Detector de anomalias por z-score rolling.
- Aprende "normal" del 70% inicial.
- Detecta desviaciones en el 30% final.
- Test sintetico: inyecta anomalias y verifica deteccion.
"""
import json
import math
from pathlib import Path
from datetime import datetime, timezone
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "data" / "raw" / "bitaxe_samples.marked.jsonl"

# Features a vigilar y direccion de la anomalia
FEATURES = {
    "temp": {"direction": "high", "abs_min": 3.0},
    "vrTemp": {"direction": "high", "abs_min": 3.0},
    "power": {"direction": "high", "abs_min": 2.0},
    "errorPercentage": {"direction": "high", "abs_min": 2.0},
    "wifiRSSI": {"direction": "low", "abs_min": 10.0},
    "hashRate": {"direction": "low", "abs_min": 100.0},
}

WINDOW = 5          # muestras para el promedio rolling
Z_THRESHOLD = 3.0   # desviaciones tipicas para marcar anomalia
MIN_VALID = 100     # minimo de muestras para aprender


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


def num(o, k):
    v = o.get(k)
    if isinstance(v, (int, float)) and math.isfinite(v):
        return float(v)
    return None


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
            if dt is None:
                continue
            o["_dt"] = dt
            samples.append(o)
    samples.sort(key=lambda x: x["_dt"])
    print(f"Samples: {len(samples)}")
    if len(samples) < MIN_VALID * 2:
        print("Pocos samples para train/test.")
        return

    split = int(len(samples) * 0.7)
    train = samples[:split]
    test = samples[split:]
    print(f"Train: {len(train)} | Test: {len(test)}")

    # ---- Aprender distribucion normal del train ----
    print("\n=== Aprendiendo estado normal (train) ===")
    stats = {}
    for feat, cfg in FEATURES.items():
        direction = cfg["direction"]
        abs_min = cfg["abs_min"]
        vals = [num(s, feat) for s in train]
        vals = [v for v in vals if v is not None]
        if len(vals) < MIN_VALID:
            print(f"  {feat:20s} sin datos suficientes, se omite")
            continue
        arr = np.array(vals)
        stats[feat] = {
            "mean": float(arr.mean()),
            "std": float(arr.std()) + 1e-8,
            "p01": float(np.percentile(arr, 1)),
            "p99": float(np.percentile(arr, 99)),
            "direction": direction,
            "abs_min": abs_min,
        }
        print(f"  {feat:20s} mean={arr.mean():8.2f} std={arr.std():8.2f} "
              f"p01={np.percentile(arr, 1):8.2f} p99={np.percentile(arr, 99):8.2f}")

    # ---- Funcion de deteccion ----
    def detect(samples_list, label):
        flags = []
        for feat, info in stats.items():
            direction = info["direction"]
            # Rolling mean para suavizar ruido
            values = [num(s, feat) for s in samples_list]
            for i in range(WINDOW, len(values)):
                window = values[i - WINDOW:i]
                if any(v is None for v in window):
                    continue
                wmean = sum(window) / WINDOW
                z = (wmean - info["mean"]) / info["std"]
                abs_dev = abs(wmean - info["mean"])
                # Requiere TAMBIEN desviacion absoluta minima (evita features casi constantes)
                if abs_dev < info["abs_min"]:
                    continue
                if direction == "high" and z > Z_THRESHOLD:
                    flags.append({
                        "ts": samples_list[i].get("timestamp"),
                        "feature": feat,
                        "value": wmean,
                        "z": z,
                        "type": "high",
                    })
                elif direction == "low" and z < -Z_THRESHOLD:
                    flags.append({
                        "ts": samples_list[i].get("timestamp"),
                        "feature": feat,
                        "value": wmean,
                        "z": z,
                        "type": "low",
                    })
        print(f"\n  {label}: {len(flags)} flags")
        by_feat = {}
        for f in flags:
            by_feat.setdefault(f["feature"], []).append(f)
        for feat, fl in by_feat.items():
            print(f"    {feat:20s} {len(fl):4d} alertas")
            for f in fl[:3]:
                print(f"      {f['ts']}  value={f['value']:.2f}  z={f['z']:+.2f}")
        return flags

    # ---- Detectar en test real ----
    print("\n=== Deteccion en TEST (datos reales) ===")
    real_flags = detect(test, "test real")

    # ---- Test sintetico: inyectar anomalias ----
    print("\n=== Test sintetico: inyectando anomalias ===")
    synthetic = [dict(s) for s in test]

    # Inyectar: 5 muestras con temp +20C
    for i in range(100, 105):
        if i < len(synthetic) and num(synthetic[i], "temp") is not None:
            synthetic[i] = dict(synthetic[i])
            synthetic[i]["temp"] = num(synthetic[i], "temp") + 20

    # Inyectar: 5 muestras con wifi a -95
    for i in range(500, 505):
        if i < len(synthetic) and num(synthetic[i], "wifiRSSI") is not None:
            synthetic[i] = dict(synthetic[i])
            synthetic[i]["wifiRSSI"] = -95.0

    # Inyectar: 5 muestras con hashrate a la mitad
    for i in range(900, 905):
        if i < len(synthetic) and num(synthetic[i], "hashRate") is not None:
            synthetic[i] = dict(synthetic[i])
            synthetic[i]["hashRate"] = num(synthetic[i], "hashRate") * 0.5

    print(f"  Inyectadas: temp+20C @ idx 100-104, wifi-95 @ 500-504, hashrate/2 @ 900-904")
    synth_flags = detect(synthetic, "test sintetico")

    # ---- Diagnostico: detecto las inyecciones? ----
    print("\n=== Verificacion de deteccion ===")
    checks = [
        ("temp @ idx 100-104", "temp", "high", synthetic[100:105]),
        ("wifi @ idx 500-504", "wifiRSSI", "low", synthetic[500:505]),
        ("hashRate @ idx 900-904", "hashRate", "low", synthetic[900:905]),
    ]
    for label, feat, direction, injected in checks:
        detected = [f for f in synth_flags
                    if f["feature"] == feat and f["type"] == direction]
        # Verificar si alguno cae cerca de la ventana inyectada
        print(f"  {label:30s} -> {len(detected)} alertas en '{feat}/{direction}'")

    # ---- Tasa de falsos positivos ----
    if real_flags:
        unique_minutes = len(set(f["ts"] for f in real_flags))
        total_min = len(test)
        fpr = 100.0 * unique_minutes / total_min
        print(f"\n=== Falsos positivos en test real ===")
        print(f"  {unique_minutes} minutos con alerta de {total_min} ({fpr:.2f}%)")
        print(f"  (Si es 0-1%, detector sano. Si >5%, umbral demasiado bajo.)")

    print("\n=== Resumen ===")
    print(f"  Features vigiladas: {list(stats.keys())}")
    print(f"  Umbral z: {Z_THRESHOLD}σ  |  Ventana rolling: {WINDOW}")
    print(f"  Alertas reales: {len(real_flags)}")
    print(f"  Alertas sinteticas: {len(synth_flags)}")

    # Guardar modelo para uso futuro
    model_path = ROOT / "data" / "processed" / "anomaly_model.json"
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model_path.write_text(json.dumps({
        "features": stats,
        "z_threshold": Z_THRESHOLD,
        "window": WINDOW,
        "trained_on": len(train),
    }, indent=2))
    print(f"\nModelo guardado: {model_path}")


if __name__ == "__main__":
    main()
