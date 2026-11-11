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

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply", action="store_true",
        help="autoriza aplicar el ajuste propuesto al minero"
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

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
