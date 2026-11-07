#!/usr/bin/env python3
"""
Prueba de Undervolting Controlado.
Baja de 1150 mV a 1100 mV manteniendo 525 MHz.
Mide hashrate, temperatura y shares rechazados.
"""
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import os
BITAXE = f"http://{os.environ.get('BITAXE_IP', '192.168.1.100')}"
LOG = Path("data/raw/bitaxe_undervolt_test.jsonl")
FREQ = 525
ORIG_VOLT = 1150
TEST_VOLT = 1100
WAIT_SEC = 90  # 90 segundos para ver si aparecen shares rechazados

def get_json(path):
    with urllib.request.urlopen(f"{BITAXE}{path}", timeout=10) as r:
        return json.loads(r.read().decode())

def patch_json(path, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(f"{BITAXE}{path}", data=data, method="PATCH", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        r.read()
        return {"status": r.status}

def read_state():
    d = get_json("/api/system/info")
    return {
        "frequency": d.get("frequency"),
        "coreVoltage": d.get("coreVoltage"),
        "hashRate": d.get("hashRate"),
        "power": d.get("power"),
        "temp": d.get("temp"),
        "vrTemp": d.get("vrTemp"),
        "sharesAccepted": d.get("sharesAccepted"),
        "sharesRejected": d.get("sharesRejected")
    }

def log_event(kind, before, after, reason):
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "kind": kind,
        "before": before,
        "after": after,
        "reason": reason
    }
    with LOG.open("a") as f:
        f.write(json.dumps(entry) + "\n")

def main():
    print("▶ Estado inicial:")
    before = read_state()
    print(f"  {before}")
    
    if before["coreVoltage"] != ORIG_VOLT:
        print(f"⚠️  El Bitaxe no está a {ORIG_VOLT} mV. Abortando.")
        return

    print(f"\n▶ Aplicando UNDERVOLTING: {TEST_VOLT} mV @ {FREQ} MHz...")
    try:
        patch_json("/api/system", {"frequency": FREQ, "coreVoltage": TEST_VOLT})
        time.sleep(5)
        print(f"  Comando aceptado. Esperando {WAIT_SEC}s para medir estabilidad...")
    except Exception as e:
        print(f"  ❌ Error enviando comando: {e}")
        return

    for _ in range(WAIT_SEC):
        time.sleep(1)
        print(".", end="", flush=True)
    print(" Listo.")

    mid = read_state()
    print(f"\n▶ Estado durante Undervolting ({TEST_VOLT} mV):")
    print(f"  {mid}")
    
    # Cálculo de eficiencia
    if mid["hashRate"] and mid["power"]:
        eff = mid["power"] / (mid["hashRate"] / 1000)
        print(f"  📊 Eficiencia: {eff:.2f} J/TH")
    
    # Verificar shares rechazados
    rej_diff = mid["sharesRejected"] - before["sharesRejected"]
    if rej_diff > 0:
        print(f"  ⚠️  ALERTA: {rej_diff} shares rechazados. El voltaje es inestable.")
    else:
        print(f"  ✅ Cero shares rechazados. Estable.")

    print(f"\n▶ Restaurando a {ORIG_VOLT} mV (por seguridad)...")
    try:
        patch_json("/api/system", {"frequency": FREQ, "coreVoltage": ORIG_VOLT})
        time.sleep(5)
        final = read_state()
        log_event("undervolt_test", before, mid, "prueba finalizada, revertido a 1150")
        print(f"  Restauración: {final}")
    except Exception as e:
        print(f"  ❌ Error restaurando: {e}")

    print(f"\n📁 Log guardado en: {LOG}")

if __name__ == "__main__":
    main()
