#!/usr/bin/env python3
"""
Detector de Deriva de Nonces del Bitaxe (Capa 2).
Preparado para cuando exista acceso a nonces del pool.

Estados:
- SIN DATOS: no hay pool configurado.
- MOCK: usa datos simulados para demostrar el motor.
- LIVE: usa datos reales del pool (futuro).

Activar LIVE requiere:
1. Pool con API de shares (Braiins, Public Pool, Ocean...).
2. Configurar POOL_API_URL y POOL_WORKER_ID abajo.
3. Cambiar MODE = "live".
"""
import json
import urllib.request
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import random

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "data" / "processed" / "nonce_drift_bitaxe.json"

# ============ CONFIGURACION ============
MODE = "mock"  # "mock" | "live" | "no_data"
POOL_API_URL = ""  # Ej: "https://pool.braiins.com/api/v1/workers/USERNAME"
POOL_WORKER_ID = ""  # Ej: "hp_lapto1234"

# Referencia: distribucion historica de Bitcoin (ya la tenemos)
HISTORIC = ROOT / "data" / "processed" / "nonces_10k.json"


def load_historic_distribution():
    """Carga los 10k nonces historicos como referencia."""
    if not HISTORIC.exists():
        return []
    with open(HISTORIC) as f:
        data = json.load(f)
    return [r["nonce"] for r in data]


def fetch_pool_nonces():
    """
    Descarga los nonces del pool.
    
    FORMATO ESPERADO (cuando esté disponible):
    JSON con estructura:
    {
      "shares": [
        {"nonce": 123456, "difficulty": 512, "timestamp": "..."},
        ...
      ]
    }
    
    Adaptar el parser segun el pool.
    """
    if not POOL_API_URL or not POOL_WORKER_ID:
        return None, "Pool API no configurado"
    
    try:
        req = urllib.request.Request(
            POOL_API_URL,
            headers={"User-Agent": "TEOS-Neurona/1.0"}
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        
        # Adaptar segun el pool:
        shares = data.get("shares", [])
        nonces = [s["nonce"] for s in shares if "nonce" in s]
        return nonces, None
    except Exception as e:
        return None, f"Error conectando al pool: {e}"


def generate_mock_nonces(n=500):
    """
    Genera nonces simulados para demostrar el motor.
    En el futuro, estos vendran del pool real.
    """
    # Simulamos 3 escenarios posibles:
    scenarios = [
        ("NORMAL", lambda: random.randint(0, 2**32 - 1)),
        ("ATENCION", lambda: random.randint(0, 2**30)),  # Sesgo hacia abajo
        ("ALERTA", lambda: random.randint(2**30, 2**31)),  # Concentrado en un rango
    ]
    
    # Elegimos uno al azar para la demo (normalmente seria "NORMAL")
    scenario_name, generator = random.choice(scenarios)
    nonces = [generator() for _ in range(n)]
    return nonces, scenario_name


def kolmogorov_smirnov_test(sample1, sample2):
    """Test KS para comparar dos distribuciones."""
    s1 = np.sort(sample1) / (2**32)
    s2 = np.sort(sample2) / (2**32)
    
    n1, n2 = len(s1), len(s2)
    all_values = np.concatenate([s1, s2])
    cdf1 = np.searchsorted(s1, all_values, side='right') / n1
    cdf2 = np.searchsorted(s2, all_values, side='right') / n2
    
    return float(np.max(np.abs(cdf1 - cdf2)))


def interpret_ks(ks_stat):
    """Traduce el estadistico KS a un veredicto."""
    if ks_stat < 0.05:
        return "NORMAL", "green", "Distribucion de nonces alineada con la red Bitcoin."
    elif ks_stat < 0.10:
        return "ATENCION", "yellow", "Ligera desviacion. Revisar rendimiento del pool."
    elif ks_stat < 0.20:
        return "ALERTA", "orange", "Desviacion significativa. Posible sesgo del pool o firmware."
    else:
        return "ANOMALIA", "red", "Anomalia fuerte. La distribucion de nonces del pool es atipica."


def main():
    print("=" * 60)
    print("  TEOS NONCE DRIFT DETECTOR - CAPA 2 (Bitaxe)")
    print("=" * 60)
    print(f"  Modo actual: {MODE.upper()}")
    print()

    historic = load_historic_distribution()
    if not historic:
        print("❌ ERROR: No existen los 10k nonces historicos.")
        print("   Ejecuta primero: python3 tools/nonce_lab.py")
        return

    print(f"[1] Referencia historica: {len(historic)} nonces de Bitcoin")

    if MODE == "no_data":
        result = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "SIN_DATOS",
            "message": "Pool no configurado. Este modulo se activara cuando conectes un pool con API de shares.",
            "how_to_activate": [
                "1. Elegir un pool con API publica de shares (Braiins, Public Pool, Ocean).",
                "2. Configurar POOL_API_URL y POOL_WORKER_ID en tools/nonce_drift_bitaxe.py",
                "3. Cambiar MODE = 'live' y reiniciar el scheduler.",
            ]
        }
        with open(OUTPUT, "w") as f:
            json.dump(result, f, indent=2)
        print("\n" + "=" * 60)
        print("  ESTADO: SIN DATOS")
        print("=" * 60)
        print(result["message"])
        return

    # Obtener nonces segun modo
    if MODE == "live":
        print("[2] Descargando nonces del pool...")
        recent, error = fetch_pool_nonces()
        if error:
            print(f"  ❌ {error}")
            print("  Cambiando a modo 'no_data' temporalmente.")
            result = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": "SIN_DATOS",
                "message": error,
            }
            with open(OUTPUT, "w") as f:
                json.dump(result, f, indent=2)
            return
        print(f"  ✅ {len(recent)} nonces del pool")
        scenario = "LIVE"
    else:  # mock
        print("[2] Generando nonces simulados (MOCK)...")
        recent, scenario = generate_mock_nonces(500)
        print(f"  Escenario simulado: {scenario}")
        print(f"  Generados: {len(recent)} nonces de prueba")

    print("\n[3] Estadisticas comparativas:")
    hist_mean = np.mean(historic)
    hist_std = np.std(historic)
    recent_mean = np.mean(recent)
    recent_std = np.std(recent)
    print(f"  Historico Bitcoin: media={hist_mean:,.0f} std={hist_std:,.0f}")
    print(f"  Bitaxe:            media={recent_mean:,.0f} std={recent_std:,.0f}")

    print("\n[4] Aplicando test Kolmogorov-Smirnov...")
    ks = kolmogorov_smirnov_test(recent, historic)
    verdict, color, message = interpret_ks(ks)
    print(f"  KS statistic: {ks:.4f}")
    print(f"  Veredicto: {verdict}")
    print(f"  Mensaje: {message}")

    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": MODE,
        "status": verdict,
        "color": color,
        "message": message,
        "ks_statistic": round(ks, 4),
        "recent_count": len(recent),
        "recent_mean": int(recent_mean),
        "recent_std": int(recent_std),
        "historic_mean": int(hist_mean),
        "historic_std": int(hist_std),
        "scenario": scenario if MODE == "mock" else None,
        "note": "MODO MOCK: datos simulados para demostracion" if MODE == "mock" else "MODO LIVE: datos reales del pool"
    }

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print(f"\n✅ Resultado guardado en {OUTPUT}")
    if MODE == "mock":
        print("\n⚠️  NOTA: Estás en MODO MOCK. Los datos son simulados.")
        print("   Para activar el modo real, configura POOL_API_URL en este script.")


if __name__ == "__main__":
    main()
