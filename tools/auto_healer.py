#!/usr/bin/env python3
"""
TEOS Auto-Healer v1.0 — Limitado y seguro.
- Verifica servicios systemd, collector y Bitaxe.
- Si algo está caído, lo reinicia (solo systemctl restart).
- Modo por defecto: SIMULACION (solo reporta).
- Para actuar de verdad: --execute
- Log: data/healer/healer_log.jsonl
"""
import json
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "data" / "healer" / "healer_log.jsonl"
BITAXE_IP = "192.168.1.100"
SERVICES = [
    "teos-nexus-collector.service",
    "teos-neurona-scheduler.service",
    "teos-neurona-api.service",
]
EXECUTE = "--execute" in sys.argv


def log_event(kind, detail):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "kind": kind,
        "detail": detail,
        "mode": "execute" if EXECUTE else "simulate",
    }
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"[{entry['ts'][:19]}] {kind}: {detail}")


def service_active(name):
    r = subprocess.run(
        ["systemctl", "is-active", name],
        capture_output=True, text=True, timeout=5,
    )
    return r.stdout.strip() == "active"


def restart_service(name):
    if not EXECUTE:
        log_event("WOULD_RESTART", name)
        return
    r = subprocess.run(
        ["sudo", "systemctl", "restart", name],
        capture_output=True, text=True, timeout=30,
    )
    if r.returncode == 0:
        log_event("RESTARTED", name)
    else:
        log_event("RESTART_FAILED", f"{name}: {r.stderr.strip()}")


def check_bitaxe():
    try:
        with urllib.request.urlopen(
            f"http://{BITAXE_IP}/api/system/info", timeout=5
        ) as r:
            return r.status == 200
    except Exception:
        return False


def check_collector_fresh(max_age_s=300):
    try:
        import os
        mtime = os.path.getmtime(ROOT / "data" / "raw" / "bitaxe_samples.marked.jsonl")
        age = time.time() - mtime
        return age <= max_age_s, int(age)
    except Exception:
        return False, -1


def run_once():
    issues = 0
    for svc in SERVICES:
        if not service_active(svc):
            log_event("SERVICE_DOWN", svc)
            restart_service(svc)
            issues += 1
    if not check_bitaxe():
        log_event("BITAXE_DOWN", BITAXE_IP)
        issues += 1
    fresh, age = check_collector_fresh()
    if not fresh:
        log_event("COLLECTOR_STALE", f"age={age}s")
        issues += 1
    if issues == 0:
        log_event("ALL_OK", "3 servicios + Bitaxe + collector frescos")


def main():
    print(f"=== TEOS Auto-Healer v1.0 ===")
    print(f"Modo: {'EXECUTE (actua)' if EXECUTE else 'SIMULATE (solo reporta)'}")
    print(f"Bitaxe: {BITAXE_IP}")
    print(f"Servicios vigilados: {len(SERVICES)}")
    print(f"Log: {LOG}")
    print(f"Detener con Ctrl+C")
    print()
    try:
        while True:
            run_once()
            time.sleep(300)  # cada 5 min
    except KeyboardInterrupt:
        print("\nAuto-healer detenido.")


if __name__ == "__main__":
    main()
