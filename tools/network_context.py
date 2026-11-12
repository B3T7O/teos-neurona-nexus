#!/usr/bin/env python3
"""
TEOS Network Context Analyzer.
Analiza el estado de la red Bitcoin (NO predice el futuro, solo lo contextualiza):
- Proyeccion de dificultad
- Congestion del mempool
- Comisiones actuales
- Tiempos de los ultimos 10 bloques
"""
import json
import urllib.request
from pathlib import Path
from datetime import datetime, timezone
from statistics import mean, stdev

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "data" / "processed" / "network_context.json"
API = "https://mempool.space/api"

def fetch_json(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read())

def fetch_text(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return r.read().decode().strip()

def main():
    print("=" * 60)
    print("  TEOS NETWORK CONTEXT - ANALISIS DE RED BITCOIN")
    print("=" * 60)

    print("\n[1] Analizando proyeccion de dificultad...")
    diff = fetch_json(f"{API}/v1/difficulty-adjustment")
    progress = diff.get("progressPercent", 0)
    change = diff.get("difficultyChange", 0)
    remaining_blocks = diff.get("remainingBlocks", 0)
    remaining_time_ms = diff.get("remainingTime", 0)
    remaining_days = remaining_time_ms / 86400000 if remaining_time_ms else 0
    time_avg_min = diff.get("timeAvg", 600000) / 60000
    next_height = diff.get("nextRetargetHeight", 0)

    print(f"    Progreso epoch: {progress:.1f}%")
    print(f"    Cambio estimado: {change:+.2f}%")
    print(f"    Bloques restantes: {remaining_blocks}")
    print(f"    Tiempo restante: {remaining_days:.1f} dias")
    print(f"    Tiempo promedio bloque: {time_avg_min:.2f} min")
    print(f"    Proximo ajuste en bloque: {next_height}")

    print("\n[2] Analizando mempool...")
    mempool = fetch_json(f"{API}/mempool")
    count = mempool.get("count", 0)
    vsize = mempool.get("vsize", 0)
    total_fee = mempool.get("total_fee", 0)

    if count < 5000:
        congestion = "BAJA"
    elif count < 30000:
        congestion = "MEDIA"
    else:
        congestion = "ALTA"

    print(f"    Transacciones pendientes: {count:,}")
    print(f"    Tamano: {vsize/1e6:.1f} MB")
    print(f"    Comisiones totales: {total_fee/1e8:.4f} BTC")
    print(f"    Congestion: {congestion}")

    print("\n[3] Analizando comisiones recomendadas...")
    fees = fetch_json(f"{API}/v1/fees/recommended")
    fastest = fees.get("fastestFee", 0)
    half_hour = fees.get("halfHourFee", 0)
    hour = fees.get("hourFee", 0)
    economy = fees.get("economyFee", 0)
    minimum = fees.get("minimumFee", 0)

    print(f"    Rapida: {fastest} sat/vB")
    print(f"    30 min: {half_hour} sat/vB")
    print(f"    1 hora: {hour} sat/vB")
    print(f"    Economica: {economy} sat/vB")

    print("\n[4] Analizando ultimos 10 bloques...")
    height = int(fetch_text(f"{API}/blocks/tip/height"))
    block_times = []
    for i in range(10):
        try:
            bh = fetch_text(f"{API}/block-height/{height - i}")
            b = fetch_json(f"{API}/block/{bh}")
            block_times.append(b.get("timestamp", 0))
        except Exception:
            continue

    intervals = []
    for i in range(len(block_times) - 1):
        intervals.append((block_times[i] - block_times[i+1]) / 60)

    if intervals:
        avg_interval = mean(intervals)
        std_interval = stdev(intervals) if len(intervals) > 1 else 0
        print(f"    Tiempo promedio: {avg_interval:.2f} min")
        print(f"    Desviacion: {std_interval:.2f} min")
        print(f"    Objetivo: 10.00 min")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "difficulty": {
            "progress_pct": round(progress, 2),
            "estimated_change_pct": round(change, 2),
            "remaining_blocks": remaining_blocks,
            "remaining_days": round(remaining_days, 2),
            "avg_block_time_min": round(time_avg_min, 2),
            "next_retarget_height": next_height,
        },
        "mempool": {
            "tx_count": count,
            "size_mb": round(vsize / 1e6, 2),
            "total_fee_btc": round(total_fee / 1e8, 4),
            "congestion": congestion,
        },
        "fees": {
            "fastest": fastest,
            "half_hour": half_hour,
            "hour": hour,
            "economy": economy,
            "minimum": minimum,
        },
        "recent_blocks": {
            "count": len(intervals),
            "avg_interval_min": round(avg_interval, 2) if intervals else 0,
            "std_interval_min": round(std_interval, 2) if len(intervals) > 1 else 0,
        }
    }

    with OUTPUT.open("w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print(f"\nOK: Datos guardados en {OUTPUT}")

if __name__ == "__main__":
    main()
