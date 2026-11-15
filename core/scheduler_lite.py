#!/usr/bin/env python3
"""
Scheduler Lite - Tareas de monitoreo rápido cada 2 minutos.
Delegado del scheduler principal para evitar sobrecarga.
"""
import time
import traceback
from datetime import datetime
from core.bitaxe_control import main as run_bitaxe_control
from tools.pulse_series import main as run_pulse_series
from tools.network_context import main as run_network_context
from core.evolution_history import record as _evo_record

INTERVAL = 120  # 2 minutos


def main():
    print("TEOS SCHEDULER LITE: monitoreo rápido")
    print(f"Intervalo: {INTERVAL}s (2 min)")
    try:
        while True:
            started = time.monotonic()
            print(f"\n[{datetime.now().astimezone().isoformat()}] Lite tick")

            try:
                run_bitaxe_control()
                _evo_record("bitaxe_control", "ok", "lite scheduler")
            except Exception:
                _evo_record("bitaxe_control", "failed", "error en lite")
                traceback.print_exc()

            try:
                run_pulse_series()
                _evo_record("pulse_series", "ok", "lite scheduler")
            except Exception:
                _evo_record("pulse_series", "failed", "error en lite")
                traceback.print_exc()

            try:
                run_network_context()
                _evo_record("network_context", "ok", "lite scheduler")
            except Exception:
                _evo_record("network_context", "failed", "error en lite")
                traceback.print_exc()

            elapsed = time.monotonic() - started
            time.sleep(max(10, INTERVAL - elapsed))
    except KeyboardInterrupt:
        print("\nScheduler Lite detenido.")


if __name__ == "__main__":
    main()
