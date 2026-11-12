#!/usr/bin/env python3
"""
Verificador de Raiz de Merkle de un bloque real de Bitcoin.
Descarga el bloque mas reciente desde mempool.space y recalcula
el Arbol de Merkle desde cero para validar su integridad.
"""
import hashlib
import json
import urllib.request

API = "https://mempool.space/api"


def sha256d(data: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


def fetch_json(url: str):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read())


def fetch_text(url: str) -> str:
    with urllib.request.urlopen(url, timeout=30) as r:
        return r.read().decode().strip()


def compute_merkle_root(txids_hex):
    # Los TXIDs se muestran en big-endian (display). Internamente
    # Bitcoin usa little-endian, asi que invertimos cada uno.
    level = [bytes.fromhex(txid)[::-1] for txid in txids_hex]

    while len(level) > 1:
        # Si es impar, duplicamos el ultimo (regla de Bitcoin)
        if len(level) % 2 == 1:
            level.append(level[-1])

        next_level = []
        for i in range(0, len(level), 2):
            next_level.append(sha256d(level[i] + level[i + 1]))
        level = next_level

    # Convertimos de little-endian interno a big-endian display
    return level[0][::-1].hex()


def main():
    print("=" * 60)
    print("  VERIFICADOR DE RAIZ DE MERKLE - BITCOIN EN VIVO")
    print("=" * 60)

    print("\n[1] Consultando la altura del bloque actual...")
    height = int(fetch_text(f"{API}/blocks/tip/height"))
    print(f"    Altura: {height}")

    print(f"\n[2] Obteniendo hash del bloque {height}...")
    block_hash = fetch_text(f"{API}/block-height/{height}")
    print(f"    Hash: {block_hash}")

    print(f"\n[3] Descargando cabecera del bloque...")
    block = fetch_json(f"{API}/block/{block_hash}")
    declared_root = block["merkle_root"]
    n_tx = block["tx_count"]
    print(f"    Merkle Root declarada: {declared_root}")
    print(f"    Transacciones: {n_tx}")
    print(f"    Tamano: {block['size']:,} bytes")

    print(f"\n[4] Descargando los {n_tx} TXIDs del bloque...")
    txids = fetch_json(f"{API}/block/{block_hash}/txids")
    print(f"    TXIDs recibidos: {len(txids)}")

    print(f"\n[5] Recalculando el Arbol de Merkle (SHA256d)...")
    computed_root = compute_merkle_root(txids)
    print(f"    Merkle Root calculada: {computed_root}")

    print("\n" + "=" * 60)
    print("  RESULTADO")
    print("=" * 60)
    if computed_root == declared_root:
        print("  ✅ VERIFICACION EXITOSA")
        print("     La raiz calculada coincide con la declarada.")
        print("     El bloque es criptograficamente integro.")
        print(f"     {n_tx} transacciones caben en un solo hash de 32 bytes.")
    else:
        print("  ❌ VERIFICACION FALLIDA")
        print("     Las raices no coinciden. Alguien altero el bloque.")


if __name__ == "__main__":
    main()
