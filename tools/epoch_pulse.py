#!/usr/bin/env python3
"""
ECG de Bitcoin: Visualiza el pulso de ajuste de dificultad.
Descarga los ultimos 20 epochs (2016 bloques cada uno) y grafica
el tiempo promedio por bloque y el cambio de dificultad.
"""
import json
import urllib.request
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "data" / "processed" / "epoch_pulse.png"
OUTPUT_JSON = ROOT / "data" / "processed" / "epoch_pulse.json"
API = "https://mempool.space/api"
EPOCH = 2016
NUM_EPOCHS = 20

def fetch_json(url):
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            return json.loads(r.read())
    except:
        return None

def fetch_text(url):
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            return r.read().decode().strip()
    except:
        return None

def main():
    print("[1] Obteniendo altura actual...")
    current = int(fetch_text(f"{API}/blocks/tip/height"))
    print(f"    Altura actual: {current}")

    # Calcular el bloque de inicio del epoch actual
    current_epoch_start = (current // EPOCH) * EPOCH
    print(f"    Epoch actual empieza en bloque: {current_epoch_start}")

    epochs_data = []

    print(f"[2] Descargando datos de los ultimos {NUM_EPOCHS} epochs...")
    for i in range(NUM_EPOCHS):
        # El epoch anterior al actual es current_epoch_start - (i+1)*EPOCH
        prev_start = current_epoch_start - (i + 1) * EPOCH
        curr_start = current_epoch_start - i * EPOCH
        if prev_start < 0:
            break

        # Obtener los timestamps de los bloques de inicio y fin del epoch
        prev_bh = fetch_text(f"{API}/block-height/{prev_start}")
        curr_bh = fetch_text(f"{API}/block-height/{curr_start}")
        if not prev_bh or not curr_bh:
            continue

        prev_block = fetch_json(f"{API}/block/{prev_bh}")
        curr_block = fetch_json(f"{API}/block/{curr_bh}")
        if not prev_block or not curr_block:
            continue

        elapsed = curr_block["timestamp"] - prev_block["timestamp"]
        avg_block_time = elapsed / EPOCH / 60  # en minutos

        # Cambio de dificultad: si el tiempo promedio es menor a 10 min, sube.
        # Formula: (target_time / real_time - 1) * 100
        target_time = 10 * 60  # 600 segundos
        actual_avg = elapsed / EPOCH
        change_pct = (target_time / actual_avg - 1) * 100

        epochs_data.append({
            "epoch_start": prev_start,
            "epoch_end": curr_start,
            "avg_block_min": round(avg_block_time, 2),
            "difficulty_change_pct": round(change_pct, 2),
            "end_timestamp": curr_block["timestamp"],
        })
        print(f"  Epoch {prev_start}-{curr_start} | Prom {avg_block_time:.2f} min | Cambio {change_pct:+.2f}%")

    # Invertir para que quede en orden cronologico
    epochs_data = list(reversed(epochs_data))

    # Guardar datos
    with open(OUTPUT_JSON, "w") as f:
        json.dump(epochs_data, f, indent=2)

    # Generar ECG
    print("\n[3] Generando ECG de Bitcoin...")
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), sharex=True)
    fig.patch.set_facecolor('#0a0e14')

    x_labels = [f"{d['epoch_start']//1000}k" for d in epochs_data]
    avg_times = [d["avg_block_min"] for d in epochs_data]
    changes = [d["difficulty_change_pct"] for d in epochs_data]

    # Grafico 1: Tiempo promedio por bloque (el pulso)
    colors = ['#3fb950' if t < 10 else '#f85149' for t in avg_times]
    ax1.bar(range(len(epochs_data)), avg_times, color=colors, alpha=0.8, edgecolor='black')
    ax1.axhline(10, color='#58a6ff', linestyle='--', lw=2, label='Objetivo: 10 min')
    ax1.set_ylabel("Tiempo promedio por bloque (min)", color='white', fontsize=11)
    ax1.set_title("ECG de Bitcoin - Pulso de Ajuste de Dificultad (Ultimos 20 epochs)", 
                  color='white', fontsize=14, pad=15)
    ax1.set_facecolor('#0a0e14')
    ax1.tick_params(colors='#8b949e')
    ax1.grid(True, linestyle='--', alpha=0.3, color='#30363d')
    ax1.legend(facecolor='#161b22', edgecolor='#30363d', labelcolor='white')
    ax1.spines['bottom'].set_color('#30363d')
    ax1.spines['left'].set_color('#30363d')
    ax1.spines['top'].set_visible(False)
    ax1.spines['right'].set_visible(False)

    # Grafico 2: Cambio de dificultad (el "voltaje" del latido)
    changes_colors = ['#3fb950' if c < 0 else '#f85149' for c in changes]
    ax2.bar(range(len(epochs_data)), changes, color=changes_colors, alpha=0.8, edgecolor='black')
    ax2.axhline(0, color='#8b949e', linestyle='-', lw=1)
    ax2.set_ylabel("Cambio de dificultad (%)", color='white', fontsize=11)
    ax2.set_xlabel("Inicio del Epoch (bloque)", color='white', fontsize=11)
    ax2.set_facecolor('#0a0e14')
    ax2.tick_params(colors='#8b949e')
    ax2.grid(True, linestyle='--', alpha=0.3, color='#30363d')
    ax2.spines['bottom'].set_color('#30363d')
    ax2.spines['left'].set_color('#30363d')
    ax2.spines['top'].set_visible(False)
    ax2.spines['right'].set_visible(False)

    ax2.set_xticks(range(len(epochs_data)))
    ax2.set_xticklabels(x_labels, rotation=45, color='#8b949e')

    plt.tight_layout()
    plt.savefig(OUTPUT, dpi=120, facecolor='#0a0e14')
    print(f"\n✅ ECG guardado en {OUTPUT}")

    # Estadisticas
    print(f"\n📊 Estadisticas del pulso:")
    print(f"   Tiempo promedio historico: {np.mean(avg_times):.2f} min")
    print(f"   Epoch mas rapido: {min(avg_times):.2f} min")
    print(f"   Epoch mas lento:  {max(avg_times):.2f} min")
    print(f"   Cambio promedio: {np.mean(changes):+.2f}%")

if __name__ == "__main__":
    main()
