#!/usr/bin/env python3
"""
Detector de Deriva de Nonces.
Compara la distribucion de los ultimos 500 nonces de bloques
contra los 10,000 historicos. Detecta cambios estadisticos.
"""
import json
import urllib.request
from pathlib import Path
from datetime import datetime, timezone
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "data" / "processed" / "nonce_drift.json"
HISTORIC = ROOT / "data" / "processed" / "nonces_10k.json"
API = "https://mempool.space/api"
RECENT_COUNT = 500

def fetch_text(url):
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return r.read().decode().strip()
    except:
        return None

def fetch_json(url):
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return json.loads(r.read())
    except:
        return None

def get_recent_nonces(count=RECENT_COUNT):
    """Descarga los nonces de los ultimos N bloques."""
    current = int(fetch_text(f"{API}/blocks/tip/height"))
    nonces = []
    for i in range(count):
        h = current - i
        bh = fetch_text(f"{API}/block-height/{h}")
        if not bh:
            continue
        b = fetch_json(f"{API}/block/{bh}")
        if b and b.get("nonce") is not None:
            nonces.append(b["nonce"])
    return nonces

def kolmogorov_smirnov_test(sample1, sample2):
    """
    Test KS simplificado: compara dos distribuciones empiricas.
    Devuelve un valor entre 0 y 1 (0 = identicas, 1 = totalmente distintas).
    """
    s1 = np.sort(sample1) / (2**32)  # Normalizar a [0, 1]
    s2 = np.sort(sample2) / (2**32)
    
    n1, n2 = len(s1), len(s2)
    all_values = np.concatenate([s1, s2])
    cdf1 = np.searchsorted(s1, all_values, side='right') / n1
    cdf2 = np.searchsorted(s2, all_values, side='right') / n2
    
    return float(np.max(np.abs(cdf1 - cdf2)))

def main():
    print("=" * 60)
    print("  TEOS NONCE DRIFT DETECTOR")
    print("=" * 60)
    
    print(f"\n[1] Cargando {HISTORIC.name}...")
    if not HISTORIC.exists():
        print(f"  ERROR: {HISTORIC} no existe. Ejecuta primero tools/nonce_lab.py")
        return
    
    with open(HISTORIC) as f:
        historic = json.load(f)
    historic_nonces = [r["nonce"] for r in historic]
    print(f"  {len(historic_nonces)} nonces historicos cargados")
    
    print(f"\n[2] Descargando {RECENT_COUNT} nonces recientes...")
    recent_nonces = get_recent_nonces(RECENT_COUNT)
    print(f"  {len(recent_nonces)} nonces recientes descargados")
    
    if len(recent_nonces) < 50:
        print("  ERROR: muy pocos nonces recientes. Reintenta mas tarde.")
        return
    
    print("\n[3] Calculando estadisticas...")
    hist_mean = np.mean(historic_nonces)
    hist_std = np.std(historic_nonces)
    recent_mean = np.mean(recent_nonces)
    recent_std = np.std(recent_nonces)
    
    print(f"  Historico: media={hist_mean:,.0f} std={hist_std:,.0f}")
    print(f"  Reciente:  media={recent_mean:,.0f} std={recent_std:,.0f}")
    
    print("\n[4] Aplicando test Kolmogorov-Smirnov...")
    ks_stat = kolmogorov_smirnov_test(recent_nonces, historic_nonces)
    print(f"  Estadistico KS: {ks_stat:.4f}")
    
    # Interpretacion (umbrales clasicos)
    if ks_stat < 0.05:
        verdict = "NORMAL"
        status_color = "green"
        message = "Los nonces recientes siguen la distribucion historica normal."
    elif ks_stat < 0.10:
        verdict = "ATENCION"
        status_color = "yellow"
        message = "Ligera desviacion. Puede ser ruido estacional o cambio gradual."
    elif ks_stat < 0.20:
        verdict = "ALERTA"
        status_color = "orange"
        message = "Desviacion significativa. Revisar si hay cambios de pools o firmware."
    else:
        verdict = "ANOMALIA"
        status_color = "red"
        message = "Anomalia fuerte. La red cambio su comportamiento de busqueda de nonces."
    
    # Comparacion con bloque genesis (sanity check)
    genesis_nonce = 2083236893
    if recent_mean < hist_mean * 0.5:
        verdict = "ANOMALIA"
        status_color = "red"
        message = "Los nonces recientes son MUY bajos. Posible cambio de estrategia global."
    
    print(f"\n  Veredicto: {verdict}")
    print(f"  Mensaje: {message}")
    
    # Guardar
    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "recent_count": len(recent_nonces),
        "historic_count": len(historic_nonces),
        "recent_mean": int(recent_mean),
        "recent_std": int(recent_std),
        "historic_mean": int(hist_mean),
        "historic_std": int(hist_std),
        "ks_statistic": round(ks_stat, 4),
        "verdict": verdict,
        "status_color": status_color,
        "message": message,
    }
    
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    
    print(f"\n✅ Resultado guardado en {OUTPUT}")

if __name__ == "__main__":
    main()
