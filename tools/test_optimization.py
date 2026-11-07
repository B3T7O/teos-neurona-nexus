#!/usr/bin/env python3
"""
Prueba controlada de optimización del Bitaxe (firmware v2.13.2).
Lee estado de /api/system/info, escribe en /api/system.
Baja a 500 MHz, espera, vuelve a 525 MHz.
"""
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import os
BITAXE = f"http://{os.environ.get('BITAXE_IP', '192.168.1.100')}"
LOG = Path("data/raw/bitaxe_control_test.jsonl")
ORIG_FREQ = 525
ORIG_VOLT = 1150
TEST_FREQ = 500
WAIT_SEC = 60


def get_json(path):
    with urllib.request.urlopen(f"{BITAXE}{path}", timeout=10) as r:
        return json.loads(r.read().decode())


def patch_json(path, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{BITAXE}{path}",
        data=data,
        method="PATCH",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        r.read()  # Ignorar body vacio del Bitaxe
        return {"status": r.status}


def read_state():
    # v2.13.2: estado actual esta en /api/system/info
    d = get_json("/api/system/info")
    return {
        "frequency": d.get("frequency"),
        "coreVoltage": d.get("coreVoltage"),
        "temp": d.get("temp"),
        "vrTemp": d.get("vrTemp"),
    }


def log_event(kind, before, after, ok, reason):
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "kind": kind,
        "before": before,
        "after": after,
        "write_attempted": True,
        "write_verified": ok,
        "reason": reason,
    }
    with LOG.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def main():
    print("▶ Estado actual:")
    before = read_state()
    print(f"  {before}")

    if before["frequency"] != ORIG_FREQ:
        print(f"⚠️  El Bitaxe no está en {ORIG_FREQ} MHz. Abortando por seguridad.")
        return

    print(f"\n▶ Bajando a {TEST_FREQ} MHz (PATCH /api/system)...")
    try:
        patch_json("/api/system", {"frequency": TEST_FREQ, "coreVoltage": ORIG_VOLT})
        time.sleep(5)
        after = read_state()
        ok = after["frequency"] == TEST_FREQ
        log_event("downgrade", before, after, ok, "prueba controlada")
        print(f"  Después: {after}")
        print(f"  ✅ Verificado" if ok else f"  ❌ No se aplicó")
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return

    print(f"\n▶ Esperando {WAIT_SEC}s con el ASIC a {TEST_FREQ} MHz...")
    for _ in range(WAIT_SEC):
        time.sleep(1)
        print(".", end="", flush=True)
    print(" Listo.")

    mid = read_state()
    print(f"\n▶ Estado a {TEST_FREQ} MHz:")
    print(f"  {mid}")

    print(f"\n▶ Restaurando a {ORIG_FREQ} MHz...")
    try:
        patch_json("/api/system", {"frequency": ORIG_FREQ, "coreVoltage": ORIG_VOLT})
        time.sleep(5)
        final = read_state()
        ok = final["frequency"] == ORIG_FREQ
        log_event("restore", mid, final, ok, "restauración tras prueba")
        print(f"  Después: {final}")
        print(f"  ✅ Verificado" if ok else f"  ❌ No se aplicó")
    except Exception as e:
        print(f"  ❌ Error: {e}")

    print(f"\n📁 Log: {LOG}")
    print("✅ Prueba completada.")


if __name__ == "__main__":
    main()
