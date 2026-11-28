#!/usr/bin/env python3
"""EXP-063 - Barrido Variacional (Frecuencias predefinidas para asegurar ejecución)"""
import json
import time
import urllib.request
from pathlib import Path
from datetime import datetime, timezone

BASE = Path(__file__).resolve().parent.parent
BITAXE_IP = "192.168.18.45"
API = f"http://{BITAXE_IP}/api/system"
LOG = BASE / "logs" / "variational_sweep.log"
RESULT = BASE / "data" / "processed" / "variational_sweep_result.json"

# Lista forzada de frecuencias para el Bitaxe Gamma 602
SWEEP_FREQS = [525, 545, 565, 575, 580, 585, 590]
SETTLE_SECONDS = 360  # 6 minutos por frecuencia (para que quepa en tu hora)
SAFE_RESTORE = 575

def log(msg):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"[{datetime.now().isoformat()}] {msg}"
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line, flush=True)

def get_info():
    with urllib.request.urlopen(f"{API}/info", timeout=15) as r:
        return json.loads(r.read())

def set_freq(freq):
    payload = json.dumps({"frequency": freq}).encode()
    req = urllib.request.Request(API, data=payload, headers={"Content-Type": "application/json"}, method="PATCH")
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.status

def measure(freq, seconds):
    samples = []
    end = time.time() + seconds
    while time.time() < end:
        try:
            d = get_info()
            samples.append({
                "hashRate": float(d.get("hashRate", 0)),
                "power": float(d.get("power", 0)),
                "temp": float(d.get("temp", 0)),
                "errorPercentage": float(d.get("errorPercentage", 0)),
            })
        except Exception as e:
            pass
        time.sleep(10)
    if not samples: return None
    n = len(samples)
    avg = {k: sum(s[k] for s in samples) / n for k in ["hashRate", "power", "temp", "errorPercentage"]}
    hr_ths = avg["hashRate"] / 1000.0 if avg["hashRate"] > 0 else 0.001
    avg["J_per_TH"] = avg["power"] / hr_ths if hr_ths > 0 else 999.0
    return avg

def main():
    log("=" * 50)
    log("EXP-063: Barrido Variacional FORZADO")
    log(f"Frecuencias a probar: {SWEEP_FREQS}")
    log(f"Duración estimada: {len(SWEEP_FREQS) * (SETTLE_SECONDS + 60) / 60:.1f} minutos")
    log("=" * 50)

    results = []
    for freq in SWEEP_FREQS:
        log(f"▶ Probando {freq} MHz...")
        try:
            set_freq(freq)
            log(f"  Esperando {SETTLE_SECONDS}s para estabilizar...")
            time.sleep(SETTLE_SECONDS)
            m = measure(freq, 60) # Medir 1 minuto
            if m:
                m["frequency"] = freq
                results.append(m)
                log(f"  ✅ {freq} MHz → HR={m['hashRate']:.0f} GH/s, P={m['power']:.1f}W, J/TH={m['J_per_TH']:.2f}")
        except Exception as e:
            log(f"  ❌ Error en {freq} MHz: {e}")

    log("\n" + "=" * 50)
    log("ANÁLISIS VARIACIONAL")
    log("=" * 50)
    best = None
    for r in results:
        log(f"Freq: {r['frequency']} MHz | HR: {r['hashRate']:.0f} | P: {r['power']:.1f}W | J/TH: {r['J_per_TH']:.2f}")
        if best is None or r["J_per_TH"] < best["J_per_TH"]:
            best = r

    if best:
        log(f"\n🏆 ESTADO FUNDAMENTAL: {best['frequency']} MHz (J/TH = {best['J_per_TH']:.2f})")

    RESULT.parent.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(json.dumps({"results": results, "ground_state": best}, indent=2))

    log(f"\n🔙 Restaurando {SAFE_RESTORE} MHz...")
    set_freq(SAFE_RESTORE)
    log("✅ Listo.")

if __name__ == "__main__":
    main()
