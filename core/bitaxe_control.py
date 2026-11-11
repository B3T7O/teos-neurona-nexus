#!/usr/bin/env python3
# Copyright (c) 2026 Luis Alberto Siguencia Andrade (B3T7O)
# SPDX-License-Identifier: Apache-2.0
#
# TEOS Neurona Nexus - Reference Implementation
# https://github.com/B3T7O/teos-neurona-nexus

"""Controlador conservador de Bitaxe Gamma. Por defecto, solo simula."""
import argparse
import json
import sys
import math
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

import os
BITAXE_IP = os.environ.get("BITAXE_IP", "192.168.1.100")
BASE = f"http://{BITAXE_IP}"
LOG = Path("data/raw/bitaxe_control.jsonl")

def get_json(path):
    with urlopen(BASE + path, timeout=5) as response:
        return json.load(response)

def patch_json(path, payload):
    request = Request(
        BASE + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="PATCH",
    )
    with urlopen(request, timeout=5) as response:
        body = response.read().decode()
        return json.loads(body) if body else {}


def read_last_samples(n=10):
    """Lee las ultimas n muestras validas de bitaxe_samples.marked.jsonl."""
    path = Path("data/raw/bitaxe_samples.marked.jsonl")
    if not path.exists():
        return []
    try:
        with path.open("rb") as f:
            f.seek(0, 2)
            size = f.tell()
            chunk = min(size, 200_000)
            f.seek(size - chunk)
            lines = f.read().decode("utf-8", errors="ignore").splitlines()
    except Exception:
        return []
    samples = []
    for ln in reversed(lines):
        ln = ln.strip()
        if not ln:
            continue
        try:
            o = json.loads(ln)
        except Exception:
            continue
        if o.get("quality") != "ok":
            continue
        samples.append(o)
        if len(samples) >= n:
            break
    return list(reversed(samples))


def predict_next_temp():
    """Predice temp(t+1) usando temp_model.json. Devuelve (pred, error_msg)."""
    model_path = Path("data/processed/temp_model.json")
    if not model_path.exists():
        return None, "temp_model.json no existe"
    try:
        model = json.loads(model_path.read_text())
    except Exception as e:
        return None, f"error leyendo modelo: {e}"
    samples = read_last_samples(n=10)
    if len(samples) < 10:
        return None, f"solo {len(samples)} muestras disponibles (necesito 10)"

    def num(o, k):
        v = o.get(k)
        if isinstance(v, (int, float)) and math.isfinite(v):
            return float(v)
        return None

    curr = samples[-1]
    t_now = num(curr, "temp")
    t_prev5 = num(samples[-6], "temp")
    t_prev10 = num(samples[-10], "temp")
    vr = num(curr, "vrTemp")
    pw = num(curr, "power")
    v = num(curr, "voltage")
    fr = num(curr, "frequency")
    hr = num(curr, "hashRate")
    if None in (t_now, t_prev5, t_prev10, vr, pw, v, fr, hr):
        return None, "faltan campos en la muestra mas reciente"
    ts = curr.get("timestamp")
    try:
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        dt = datetime.fromisoformat(ts)
    except Exception:
        return None, "timestamp invalido"
    hour = dt.hour
    dow = dt.weekday()
    feats = {
        "temp_now": t_now,
        "delta5": t_now - t_prev5,
        "delta10": t_now - t_prev10,
        "vrTemp": vr,
        "power": pw,
        "voltage": v,
        "frequency": fr,
        "hashRate": hr,
        "hour_sin": math.sin(2 * math.pi * hour / 24),
        "hour_cos": math.cos(2 * math.pi * hour / 24),
        "dow_sin": math.sin(2 * math.pi * dow / 7),
        "dow_cos": math.cos(2 * math.pi * dow / 7),
    }
    names = model.get("features", [])
    mu = model.get("mu", [])
    sigma = model.get("sigma", [])
    w = model.get("w", [])
    y_mean = model.get("y_mean", 0.0)
    if not names or len(names) != len(mu) or len(names) != len(sigma) or len(names) != len(w):
        return None, "modelo con dimensiones inconsistentes"
    x = []
    for i, name in enumerate(names):
        if name not in feats:
            return None, f"falta feature {name} en muestra actual"
        x.append((feats[name] - mu[i]) / (sigma[i] + 1e-8))
    pred = sum(xi * wi for xi, wi in zip(x, w)) + y_mean
    return pred, None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply", action="store_true",
        help="autoriza aplicar el ajuste propuesto al minero"
    )
    parser.add_argument(
        "--predictive", action="store_true",
        help="usar prediccion termica (temp_model.json) para decidir ANTES del umbral reactivo"
    )
    parser.add_argument(
        "--test-force-temp-pred", type=float, default=None,
        help="[SOLO TEST] fuerza temp_pred a un valor dado (no aplica al hardware)"
    )
    args = parser.parse_args()

    info = get_json("/api/system/info")
    asic = get_json("/api/system/asic")

    required_info = (
        "frequency", "coreVoltage", "temp", "vrTemp",
        "hashRate_10m", "expectedHashrate",
    )
    required_asic = ("frequencyOptions", "voltageOptions")

    missing = [key for key in required_info if key not in info]
    missing += [key for key in required_asic if key not in asic]
    if missing:
        raise RuntimeError(f"Respuesta AxeOS incompleta: {missing}")

    def finite_number(key):
        value = float(info[key])
        if not math.isfinite(value):
            raise RuntimeError(f"Lectura inválida de AxeOS: {key}={value}")
        return value

    freq_value = finite_number("frequency")
    voltage_value = finite_number("coreVoltage")
    if not freq_value.is_integer() or not voltage_value.is_integer():
        raise RuntimeError("Frecuencia o voltaje no son enteros válidos.")

    freq = int(freq_value)
    voltage = int(voltage_value)
    asic_temp = finite_number("temp")
    vr_temp = finite_number("vrTemp")
    hashrate = finite_number("hashRate_10m")
    expected = finite_number("expectedHashrate")

    if min(asic_temp, vr_temp, hashrate, expected) < 0:
        raise RuntimeError("AxeOS devolvió temperaturas o hashrate negativos.")
    if expected <= 0:
        raise RuntimeError("Hashrate esperado inválido.")

    allowed_freq = asic["frequencyOptions"]
    allowed_voltage = asic["voltageOptions"]
    if not isinstance(allowed_freq, list) or not isinstance(allowed_voltage, list):
        raise RuntimeError("AxeOS no devolvió listas válidas de opciones.")
    if freq not in allowed_freq or voltage not in allowed_voltage:
        raise RuntimeError("La configuración actual no coincide con las opciones AxeOS.")

    # Modo predictivo (opcional)
    temp_predicted = None
    predictive_active = getattr(args, "predictive", False)
    if predictive_active:
        if getattr(args, "test_force_temp_pred", None) is not None:
            temp_predicted = float(args.test_force_temp_pred)
            print(f"[TEST] temp_pred forzada a {temp_predicted:.3f}C")
        else:
            temp_predicted, err = predict_next_temp()
            if err:
                print(f"AVISO: modo predictivo activo pero {err}")
                temp_predicted = None

    # Política conservadora: nunca aumentar frecuencia o voltaje automáticamente.
    target_freq, target_voltage = freq, voltage
    reason = "Sin cambios: configuración actual dentro de los límites."

    if asic_temp >= 70 or vr_temp >= 80:
        lower = [f for f in allowed_freq if f < freq]
        if lower:
            target_freq = max(lower)
            reason = "Reducir frecuencia por temperatura elevada."
        else:
            reason = "Temperatura elevada; no hay frecuencia inferior disponible."
    elif predictive_active and temp_predicted is not None and temp_predicted >= 68.0:
        lower = [f for f in allowed_freq if f < freq]
        if lower:
            target_freq = max(lower)
            reason = f"Reducir frecuencia por temp predicha {temp_predicted:.2f}C >= 68C (predictivo)"
        else:
            reason = f"Temp predicha {temp_predicted:.2f}C alta; no hay frecuencia inferior disponible"
    elif hashrate < expected * 0.90:
        reason = "Hashrate muy inferior al esperado; requiere diagnóstico, no overclock automático."

    if target_freq not in allowed_freq or target_voltage not in allowed_voltage:
        raise RuntimeError("Ajuste propuesto fuera de las opciones admitidas por AxeOS.")

    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": "apply" if args.apply else "dry-run",
        "current": {
            "frequency": freq, "coreVoltage": voltage,
            "temp": asic_temp, "vrTemp": vr_temp,
            "hashRate_10m": hashrate, "expectedHashrate": expected,
        },
        "proposed": {
            "frequency": target_freq, "coreVoltage": target_voltage,
        },
        "reason": reason,
        "temp_predicted": round(temp_predicted, 4) if temp_predicted is not None else None,
        "predictive_mode": predictive_active,
    }

    try:
        if args.apply and (target_freq != freq or target_voltage != voltage):
            result["write_attempted"] = True
            patch_json("/api/system", {
                "frequency": target_freq,
                "coreVoltage": target_voltage,
            })
            after = get_json("/api/system/info")
            result["verified"] = {
                "frequency": after.get("frequency"),
                "coreVoltage": after.get("coreVoltage"),
            }
            if (after.get("frequency") != target_freq
                    or after.get("coreVoltage") != target_voltage):
                raise RuntimeError(
                    "La verificación posterior no coincide con el ajuste solicitado."
                )
            result["write_verified"] = True
        else:
            result["write_attempted"] = False
    except Exception as exc:
        result["write_verified"] = False
        result["error"] = str(exc)
        raise
    finally:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(result) + "\n")

    print(json.dumps(result, indent=2))
    if not args.apply:
        print("\nSIMULACIÓN: no se modificó el Bitaxe.")
    if predictive_active:
        if temp_predicted is not None:
            print(f"\nMODO PREDICTIVO: temp(t+1) predicha = {temp_predicted:.3f}C (umbral predictivo: 68.0C)")
        else:
            print("\nMODO PREDICTIVO: sin prediccion disponible")

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
