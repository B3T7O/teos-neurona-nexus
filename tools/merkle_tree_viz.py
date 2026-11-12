#!/usr/bin/env python3
"""
Visualizador del Arbol de Merkle de Bitcoin.
Usa el bloque 100,000 (4 transacciones) para un grafico limpio.
"""
import json
import urllib.request
import hashlib
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as patches

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "data" / "processed" / "merkle_tree.png"
API = "https://mempool.space/api"

def sha256d(data: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()

def fetch_json(url):
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read())

def fetch_text(url):
    with urllib.request.urlopen(url, timeout=10) as r:
        return r.read().decode().strip()

def main():
    print("[1] Descargando bloque historico 100,000...")
    bh = fetch_text(f"{API}/block-height/100000")
    block = fetch_json(f"{API}/block/{bh}")
    txids = fetch_json(f"{API}/block/{bh}/txids")
    
    print(f"    Merkle Root original: {block['merkle_root']}")
    print(f"    Transacciones: {len(txids)}")

    # Calcular niveles del arbol
    level_0 = [bytes.fromhex(tx)[::-1] for tx in txids]
    level_1 = [sha256d(level_0[0] + level_0[1]), sha256d(level_0[2] + level_0[3])]
    level_2 = [sha256d(level_1[0] + level_1[1])]
    
    calc_root = level_2[0][::-1].hex()
    print(f"    Merkle Root calculado: {calc_root}")
    print(f"    Coinciden: {'✅ SI' if calc_root == block['merkle_root'] else '❌ NO'}")

    # Dibujar
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 6)
    ax.axis('off')
    
    # Nodos
    nodes = {
        "root": (5, 5, f"ROOT\n{calc_root[:8]}..."),
        "h01": (2.5, 3, f"Hash\n{level_1[0][::-1].hex()[:8]}..."),
        "h23": (7.5, 3, f"Hash\n{level_1[1][::-1].hex()[:8]}..."),
        "tx0": (1.25, 1, f"TX 0\n{txids[0][:8]}..."),
        "tx1": (3.75, 1, f"TX 1\n{txids[1][:8]}..."),
        "tx2": (6.25, 1, f"TX 2\n{txids[2][:8]}..."),
        "tx3": (8.75, 1, f"TX 3\n{txids[3][:8]}..."),
    }
    
    # Lineas
    lines = [("root", "h01"), ("root", "h23"), ("h01", "tx0"), ("h01", "tx1"), ("h23", "tx2"), ("h23", "tx3")]
    for a, b in lines:
        ax.plot([nodes[a][0], nodes[b][0]], [nodes[a][1], nodes[b][1]], color='#30363d', lw=2, zorder=1)
        
    # Cajas
    colors = {"root": "#58a6ff", "h01": "#3fb950", "h23": "#3fb950", "tx0": "#8b949e", "tx1": "#8b949e", "tx2": "#8b949e", "tx3": "#8b949e"}
    for k, (x, y, label) in nodes.items():
        ax.add_patch(patches.FancyBboxPatch((x-0.7, y-0.3), 1.4, 0.6, boxstyle="round,pad=0.1", 
                                            edgecolor=colors[k], facecolor='#0d1117', lw=2, zorder=2))
        ax.text(x, y, label, ha='center', va='center', color='white', fontsize=8, zorder=3)

    plt.title("Arbol de Merkle - Bloque 100,000", fontsize=14, color='white', pad=20)
    fig.patch.set_facecolor('#0a0e14')
    ax.set_facecolor('#0a0e14')
    
    plt.tight_layout()
    plt.savefig(OUTPUT, dpi=120, facecolor='#0a0e14')
    print(f"\n✅ Grafico guardado en {OUTPUT}")

if __name__ == "__main__":
    main()
