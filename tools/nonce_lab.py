#!/usr/bin/env python3
"""
Experimento completo de Nonces:
Fase 1: Efecto Avalancha (500k secuenciales vs 500k aleatorios).
Fase 2: Descarga de 10,000 nonces historicos reales y su distribucion.
"""
import hashlib
import struct
import random
import json
import urllib.request
import time
import concurrent.futures
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "data" / "processed"
API = "https://mempool.space/api"

# Cabecera del Bloque Genesis (80 bytes) - la base de la red Bitcoin
GENESIS_HEADER = bytes.fromhex(
    "0100000000000000000000000000000000000000000000000000000000000000"
    "000000003ba3edfd7a7b12b27ac72c3e67768f617fc81bc3888a51323a9fb8aa"
    "4b1e5e4a29ab5f49ffff001d1dac2b7c"
)

def sha256d(data: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()

def count_different_bits(b1: bytes, b2: bytes) -> int:
    """Cuenta cuantos bits son diferentes entre dos hashes."""
    diff = 0
    for x, y in zip(b1, b2):
        xor = x ^ y
        diff += bin(xor).count('1')
    return diff

def fase_1_avalancha():
    print("=" * 60)
    print(" FASE 1: EFECTO AVALANCHA (500k secuenciales vs 500k aleatorios)")
    print("=" * 60)
    
    print(" Generando 500,000 nonces consecutivos...")
    consec_hashes = []
    for i in range(500_000):
        nonce_bytes = struct.pack('<I', i)
        h = sha256d(GENESIS_HEADER + nonce_bytes)
        consec_hashes.append(h)
        
    print(" Generando 500,000 nonces aleatorios...")
    rand_hashes = []
    for _ in range(500_000):
        i = random.randint(0, 2**32 - 1)
        nonce_bytes = struct.pack('<I', i)
        h = sha256d(GENESIS_HEADER + nonce_bytes)
        rand_hashes.append(h)

    print(" Calculando bits cambiados (comparando con el primer hash de cada grupo)...")
    # Medimos cuantos bits cambian respecto al hash base
    base_consec = consec_hashes[0]
    base_rand = rand_hashes[0]
    
    consec_bit_diffs = [count_different_bits(base_consec, h) for h in consec_hashes]
    rand_bit_diffs = [count_different_bits(base_rand, h) for h in rand_hashes]

    avg_consec = sum(consec_bit_diffs) / len(consec_bit_diffs)
    avg_rand = sum(rand_bit_diffs) / len(rand_bit_diffs)

    print(f"\n Promedio de bits cambiados (Consecutivos): {avg_consec:.2f} de 256 bits")
    print(f" Promedio de bits cambiados (Aleatorios):   {avg_rand:.2f} de 256 bits")
    print(" (El Efecto Avalancha perfecto es 128 bits, o sea, el 50%)")

    # Grafico de la Fase 1
    plt.figure(figsize=(10, 5))
    plt.hist(consec_bit_diffs, bins=50, alpha=0.5, label='Consecutivos', color='#58a6ff', density=True)
    plt.hist(rand_bit_diffs, bins=50, alpha=0.5, label='Aleatorios', color='#f85149', density=True)
    plt.title("Efecto Avalancha en SHA256 (Bloque Genesis)")
    plt.xlabel("Bits cambiados respecto al hash base (de 256)")
    plt.ylabel("Densidad")
    plt.legend()
    plt.grid(True, linestyle='--', alpha=0.5)
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "avalanche_effect.png", dpi=120)
    print(f"\n ✅ Grafico guardado en {OUTPUT_DIR / 'avalanche_effect.png'}")


def get_block_nonce(height):
    try:
        with urllib.request.urlopen(f"{API}/block-height/{height}", timeout=10) as r:
            block_hash = r.read().decode().strip()
        with urllib.request.urlopen(f"{API}/block/{block_hash}", timeout=10) as r:
            data = json.loads(r.read())
            return {"height": height, "nonce": data.get("nonce", 0)}
    except:
        return None

def fase_2_reales():
    print("\n" + "=" * 60)
    print(" FASE 2: 10,000 NONCES REALES DE BITCOIN")
    print("=" * 60)
    
    print(" Obteniendo altura actual...")
    with urllib.request.urlopen(f"{API}/blocks/tip/height", timeout=10) as r:
        max_height = int(r.read().decode().strip())
        
    print(f" Altura actual: {max_height}. Generando muestra de 10,000 bloques...")
    # Creamos una muestra distribuida uniformemente
    heights = [int(x) for x in np.linspace(0, max_height, 10000)]
    
    results = []
    print(" Descargando nonces (esto puede tardar unos minutos)...")
    # Usamos hilos para acelerar, pero limitamos a 5 para no saturar la API
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(get_block_nonce, h): h for h in heights}
        for i, future in enumerate(concurrent.futures.as_completed(futures)):
            res = future.result()
            if res:
                results.append(res)
            if (i+1) % 1000 == 0:
                print(f"  Progreso: {i+1}/10000 bloques...")

    results.sort(key=lambda x: x["height"])
    
    # Guardar datos
    with open(OUTPUT_DIR / "nonces_10k.json", "w") as f:
        json.dump(results, f)

    nonces = [r["nonce"] for r in results]
    h_vals = [r["height"] for r in results]

    # Grafico de la Fase 2
    plt.figure(figsize=(12, 6))
    plt.scatter(h_vals, nonces, alpha=0.5, color='#3fb950', edgecolors='black', s=15)
    
    plt.title("10,000 Nonces Reales de Bitcoin (2009 - Presente)")
    plt.xlabel("Altura del Bloque")
    plt.ylabel("Nonce (Entero de 32 bits)")
    plt.gca().xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda x, p: f'{int(x/1000)}k'))
    plt.ylim(0, 4294967295)
    plt.grid(True, linestyle='--', alpha=0.5)
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "nonces_10k_scatter.png", dpi=120)
    
    print(f"\n ✅ Grafico guardado en {OUTPUT_DIR / 'nonces_10k_scatter.png'}")
    print(f" Estadisticas de los 10,000 nonces:")
    print(f"   Minimo: {min(nonces):,}")
    print(f"   Maximo: {max(nonces):,}")
    print(f"   Media:  {int(np.mean(nonces)):,}")
    print(f"   Desv.  {int(np.std(nonces)):,}")

if __name__ == "__main__":
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fase_1_avalancha()
    fase_2_reales()
    print("\n🔬 EXPERIMENTO COMPLETO.")
