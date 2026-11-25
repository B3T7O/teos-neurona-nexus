#!/usr/bin/env python3
"""
TEOS Perfect Shares Recorder
============================
Registra hitos de precisión perfecta (error = 0.00%) en
data/processed/perfect_shares.jsonl, manteniendo el formato histórico:

  {"timestamp": "ISO8601+00:00", "error_rate": 0.0,
   "shares_accepted": N, "hashrate_10m": X,
   "frequency": N, "temp": X}

Lógica de registro (anti-spam):
  - Lee el Bitaxe cada INTERVAL segundos.
  - Solo escribe si errorPercentage <= ERROR_TOLERANCE.
  - Fuerza escritura si:
      * No hay entrada previa, o
      * La frecuencia cambió, o
      * Shares subieron >= MIN_SHARES_DELTA, o
      * Pasaron >= MIN_GAP segundos desde el último hito.

Uso:
  python3 tools/perfect_shares_recorder.py           # bucle continuo
  python3 tools/perfect_shares_recorder.py --once    # una sola pasada (test)

Arranque en background:
  nohup python3 -u tools/perfect_shares_recorder.py \
      >> logs/perfect_shares_recorder.log 2>&1 &
"""
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BITAXE_IP = "192.168.18.45"
OUT = Path(__file__).resolve().parent.parent / "data" / "processed" / "perfect_shares.jsonl"
LOG = Path(__file__).resolve().parent.parent / "logs" / "perfect_shares_recorder.log"

INTERVAL = 30            # segundos entre lecturas
MIN_GAP = 600            # 10 min mínimo entre hitos
MIN_SHARES_DELTA = 500   # o +500 shares desde el último hito
ERROR_TOLERANCE = 0.001  # <= 0.001% se considera "0.00%"

OUT.parent.mkdir(parents=True, exist_ok=True)
LOG.parent.mkdir(parents=True, exist_ok=True)


def log(msg):
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().isoformat()}] {msg}\n")
    print(msg, flush=True)


def fetch():
    with urllib.request.urlopen(f"http://{BITAXE_IP}/api/system/info", timeout=8) as r:
        return json.loads(r.read())


def last_entry():
    if not OUT.exists():
        return None
    last = None
    with OUT.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                last = line
    if not last:
        return None
    try:
        return json.loads(last)
    except Exception:
        return None


def should_write(last, cur):
    if last is None:
        return True, "primera entrada"
    try:
        dt = datetime.fromisoformat(last["timestamp"])
        gap = (datetime.now(timezone.utc) - dt).total_seconds()
    except Exception:
        gap = MIN_GAP + 1
    if cur["frequency"] != last.get("frequency"):
        return True, f"frecuencia {last.get('frequency')}→{cur['frequency']}"
    delta = cur["shares_accepted"] - last.get("shares_accepted", 0)
    if delta >= MIN_SHARES_DELTA:
        return True, f"shares +{delta}"
    if gap >= MIN_GAP:
        return True, f"{int(gap)}s desde último"
    return False, None


def write_entry(e):
    with OUT.open("a", encoding="utf-8") as f:
        f.write(json.dumps(e) + "\n")


def main():
    once = "--once" in sys.argv
    log("Perfect Shares Recorder iniciado" + (" (modo --once)" if once else ""))
    log(f"Vigilando {BITAXE_IP} cada {INTERVAL}s | OUT={OUT}")
    while True:
        try:
            i = fetch()
            err = i.get("errorPercentage", 0) or 0
            shares = i.get("sharesAccepted", 0)
            hr = i.get("hashRate", 0) or 0
            freq = i.get("frequency", 0)
            temp = i.get("temp", 0) or 0

            if err <= ERROR_TOLERANCE:
                cur = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "error_rate": 0.0,
                    "shares_accepted": int(shares),
                    "hashrate_10m": round(hr, 2),
                    "frequency": int(freq),
                    "temp": round(temp, 3),
                }
                ok, why = should_write(last_entry(), cur)
                if ok:
                    write_entry(cur)
                    log(f"🏆 HITO registrado ({why}) shares={shares} freq={freq} temp={temp:.2f}")
                elif once:
                    log(f"Sin hito en esta pasada (err={err:.3f}%, shares={shares})")
            else:
                if once:
                    log(f"Sin hito: errorPercentage={err:.3f}% > {ERROR_TOLERANCE}%")

            if once:
                break
            time.sleep(INTERVAL)
        except KeyboardInterrupt:
            log("Detenido por usuario")
            break
        except Exception as e:
            log(f"ERROR: {e}")
            if once:
                break
            time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
