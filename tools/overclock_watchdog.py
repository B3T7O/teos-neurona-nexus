#!/usr/bin/env python3
"""
Watchdog de seguridad para overclocking.
- Vigila cada 30s
- Si VRM > 82°C  -> baja 25 MHz y avisa
- Si ASIC > 65°C -> baja 25 MHz y avisa
- Si %error (ventana movil 5 min) > 3% -> baja 25 MHz y avisa
- Piso duro: 525 MHz. Nunca sube frecuencia.
- Usa delta de shares (ventana movil) en vez de errorPercentage instantaneo
  (esto elimina el ruido que hacia saltar el error de 0.3% a 2.5% por 1 share fallida)
"""
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BITAXE_IP = "192.168.18.45"
LOG = Path(__file__).resolve().parent.parent / "data" / "overclock_watchdog.jsonl"

VRM_LIMIT = 82.0
ASIC_LIMIT = 65.0
ERROR_WARN = 2.0        # % en ventana movil -> solo avisa
ERROR_CRITICAL = 3.0    # % en ventana movil -> baja frecuencia
MIN_FREQ = 525          # piso duro
FREQ_STEP = 25          # bajar en pasos de 25 MHz
WINDOW_SIZE = 10        # ultimas 10 lecturas (~5 min @ 30s)
INTERVAL = 30           # segundos entre lecturas

LOG.parent.mkdir(parents=True, exist_ok=True)


def log_event(kind, detail):
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "kind": kind,
        "detail": detail,
    }
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    print(f"[{entry['ts'][:19]}] {kind}: {detail}", flush=True)


def get_info():
    with urllib.request.urlopen(f"http://{BITAXE_IP}/api/system/info", timeout=8) as r:
        return json.loads(r.read())


def set_freq(freq):
    payload = json.dumps({"frequency": freq}).encode()
    req = urllib.request.Request(
        f"http://{BITAXE_IP}/api/system",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="PATCH",
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status


def main():
    log_event(
        "START",
        f"Watchdog v2 (VRM>{VRM_LIMIT}/ASIC>{ASIC_LIMIT}/Err_win>{ERROR_CRITICAL} -> "
        f"bajar {FREQ_STEP}MHz, piso {MIN_FREQ}, ventana {WINDOW_SIZE})",
    )

    _prev_ok = None
    _prev_fail = None
    history = []

    while True:
        try:
            i = get_info()
            freq = i.get("frequency", 0)
            vrm = i.get("vrTemp", 0) or 0
            asic = i.get("temp", 0) or 0
            err_inst = i.get("errorPercentage", 0) or 0
            sh_ok = i.get("sharesAccepted", 0)
            sh_fail = i.get("sharesRejected", 0)
            hr = i.get("hashRate", 0)

            # Ventana movil: delta de shares desde la ultima lectura
            if _prev_ok is not None:
                d_ok = max(0, sh_ok - _prev_ok)
                d_fail = max(0, sh_fail - _prev_fail)
                d_total = d_ok + d_fail
                if d_total > 0:
                    history.append(d_fail / d_total * 100.0)
                    history = history[-WINDOW_SIZE:]
            _prev_ok, _prev_fail = sh_ok, sh_fail

            err_win = sum(history) / len(history) if history else 0.0
            err_life = (sh_fail / (sh_ok + sh_fail) * 100.0) if (sh_ok + sh_fail) else 0.0

            print(
                f"[{datetime.now().strftime('%H:%M:%S')}] "
                f"Freq={freq} HR={hr:.0f} VRM={vrm:.1f}C ASIC={asic:.1f}C "
                f"Err_inst={err_inst:.2f}% Err_win={err_win:.2f}% Err_life={err_life:.2f}% "
                f"Shares={sh_ok}/{sh_fail}",
                flush=True,
            )

            # Decidir
            reason = None
            if vrm > VRM_LIMIT:
                reason = f"VRM {vrm:.1f}C > {VRM_LIMIT}C"
            elif asic > ASIC_LIMIT:
                reason = f"ASIC {asic:.1f}C > {ASIC_LIMIT}C"
            elif err_win > ERROR_CRITICAL:
                reason = f"Err_win {err_win:.2f}% > {ERROR_CRITICAL}%"

            if reason:
                if freq > MIN_FREQ:
                    new_freq = max(freq - FREQ_STEP, MIN_FREQ)
                    log_event("ALERT", f"{reason} -> bajando de {freq} a {new_freq} MHz")
                    try:
                        status = set_freq(new_freq)
                        log_event("ROLLBACK", f"Frecuencia bajada a {new_freq} MHz (status={status})")
                        history.clear()
                        _prev_ok = _prev_fail = None
                    except Exception as e:
                        log_event("ROLLBACK_FAILED", str(e))
                else:
                    log_event("ALERT_SAFE", f"{reason} (ya en piso {MIN_FREQ} MHz, sin accion)")
            elif err_win > ERROR_WARN:
                log_event("WARN", f"Err_win {err_win:.2f}% > {ERROR_WARN}% (vigilando, sin accion)")

            time.sleep(INTERVAL)

        except KeyboardInterrupt:
            log_event("STOP", "Watchdog detenido por usuario")
            break
        except Exception as e:
            log_event("ERROR", str(e))
            time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
