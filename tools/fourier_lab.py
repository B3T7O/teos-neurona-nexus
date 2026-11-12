#!/usr/bin/env python3
"""
Laboratorio de Frecuencias (FFT) para TEOS.
Analiza el espectro de: Nonces, Tiempos de Bloque y Hardware (Bitaxe).
"""
import json
import urllib.request
import numpy as np
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
PROCESSED = ROOT / "data" / "processed"
SAMPLES = ROOT / "data" / "raw" / "bitaxe_samples.marked.jsonl"
API = "https://mempool.space/api"

def fetch_text(url):
    with urllib.request.urlopen(url, timeout=10) as r:
        return r.read().decode().strip()

def fetch_json(url):
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read())

def get_block_times(n=500):
    print(f" Descargando tiempos de los ultimos {n} bloques...")
    current = int(fetch_text(f"{API}/blocks/tip/height"))
    times = []
    for i in range(n):
        try:
            bh = fetch_text(f"{API}/block-height/{current - i}")
            b = fetch_json(f"{API}/block/{bh}")
            times.append(b.get("timestamp", 0))
        except:
            pass
    # Calcular intervalos en minutos
    times.sort()
    intervals = [(times[i] - times[i-1]) / 60 for i in range(1, len(times))]
    return intervals

def get_hardware_data():
    print(" Leyendo telemetria del Bitaxe...")
    temps = []
    with open(SAMPLES, 'r') as f:
        for line in f:
            try:
                o = json.loads(line)
                if o.get("quality") == "ok" and o.get("temp") is not None:
                    temps.append(float(o["temp"]))
            except:
                pass
    return temps[-1000:] # Ultimas 1000 muestras

def main():
    print("=" * 60)
    print(" TEOS FOURIER LAB - ANALISIS ESPECTRAL")
    print("=" * 60)

    fig, axes = plt.subplots(3, 1, figsize=(12, 15))

    # --- 1. FOURIER DE LOS NONCES ---
    print("\n[1] Analizando frecuencias de los Nonces (10k)...")
    with open(PROCESSED / "nonces_10k.json") as f:
        nonces_data = json.load(f)
    nonces = [r["nonce"] for r in nonces_data]
    
    # Aplicar FFT
    fft_nonces = np.fft.fft(nonces)
    freqs_nonces = np.fft.fftfreq(len(nonces))
    power_nonces = np.abs(fft_nonces)**2
    
    axes[0].plot(freqs_nonces[:len(freqs_nonces)//2], power_nonces[:len(power_nonces)//2], color='#3fb950')
    axes[0].set_title("Espectro de Frecuencia: Nonces de Bitcoin (Ruido Blanco?)")
    axes[0].set_xlabel("Frecuencia (Hz)")
    axes[0].set_ylabel("Poder")
    axes[0].grid(True, linestyle='--', alpha=0.5)

    # --- 2. FOURIER DEL LATIDO DEL BLOQUE ---
    print("[2] Analizando frecuencias del Latido de Bitcoin...")
    intervals = get_block_times(500)
    fft_times = np.fft.fft(intervals)
    freqs_times = np.fft.fftfreq(len(intervals))
    power_times = np.abs(fft_times)**2
    
    axes[1].plot(freqs_times[:len(freqs_times)//2], power_times[:len(power_times)//2], color='#58a6ff')
    axes[1].set_title("Espectro de Frecuencia: Tiempos de Bloque (El Latido)")
    axes[1].set_xlabel("Frecuencia (Hz)")
    axes[1].set_ylabel("Poder")
    axes[1].grid(True, linestyle='--', alpha=0.5)

    # --- 3. FOURIER DEL RUIDO DEL BITAXE ---
    print("[3] Analizando frecuencias del Hardware (Temperatura)...")
    temps = get_hardware_data()
    # Quitar la tendencia (restar la media) para analizar solo el ruido
    temps_detrended = [t - np.mean(temps) for t in temps]
    fft_temps = np.fft.fft(temps_detrended)
    freqs_temps = np.fft.fftfreq(len(temps_detrended))
    power_temps = np.abs(fft_temps)**2
    
    axes[2].plot(freqs_temps[:len(freqs_temps)//2], power_temps[:len(power_temps)//2], color='#f85149')
    axes[2].set_title("Espectro de Frecuencia: Ruido Termico del Bitaxe")
    axes[2].set_xlabel("Frecuencia (Hz)")
    axes[2].set_ylabel("Poder")
    axes[2].grid(True, linestyle='--', alpha=0.5)

    plt.tight_layout()
    out_img = PROCESSED / "fourier_analysis.png"
    plt.savefig(out_img, dpi=120)
    print(f"\n✅ Grafico de Fourier guardado en {out_img}")
    print("Abre la imagen para ver el analisis de frecuencias.")

if __name__ == "__main__":
    main()
