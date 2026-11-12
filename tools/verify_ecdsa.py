#!/usr/bin/env python3
"""
Verificador de firmas ECDSA de Bitcoin (formato Legacy P2PKH).
Busca una transaccion con 1 input y 1 output para simplificar el Sighash.
Implementa la curva secp256k1 desde cero en Python puro.
"""
import hashlib
import json
import urllib.request

P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
A = 0
B = 7
Gx = 0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798
Gy = 0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8
G = (Gx, Gy)

def modinv(a, m):
    return pow(a, -1, m)

def point_add(p1, p2):
    if p1 is None: return p2
    if p2 is None: return p1
    x1, y1 = p1
    x2, y2 = p2
    if x1 == x2 and y1 != y2: return None
    if x1 == x2:
        m = (3 * x1 * x1 + A) * modinv(2 * y1, P) % P
    else:
        m = (y2 - y1) * modinv(x2 - x1, P) % P
    x3 = (m * m - x1 - x2) % P
    y3 = (m * (x1 - x3) - y1) % P
    return (x3, y3)

def point_mul(k, p):
    result = None
    addend = p
    while k:
        if k & 1:
            result = point_add(result, addend)
        addend = point_add(addend, addend)
        k >>= 1
    return result

def verify_ecdsa(public_key, signature, message_hash):
    r, s = signature
    if not (1 <= r < N and 1 <= s < N): return False
    z = int.from_bytes(message_hash, 'big')
    w = modinv(s, N)
    u1 = (z * w) % N
    u2 = (r * w) % N
    point = point_add(point_mul(u1, G), point_mul(u2, public_key))
    if point is None: return False
    return (point[0] % N) == r

def sha256d(data: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()

def fetch_json(url: str):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read())

def fetch_text(url: str) -> str:
    with urllib.request.urlopen(url, timeout=30) as r:
        return r.read().decode().strip()

def read_varint(data, offset):
    prefix = data[offset]
    if prefix < 0xfd: return prefix, offset + 1
    elif prefix == 0xfd: return int.from_bytes(data[offset+1:offset+3], 'little'), offset + 3
    elif prefix == 0xfe: return int.from_bytes(data[offset+1:offset+5], 'little'), offset + 5
    else: return int.from_bytes(data[offset+1:offset+9], 'little'), offset + 9

def main():
    print("=" * 60)
    print("  VERIFICADOR ECDSA (secp256k1) - TRANSACCION REAL")
    print("=" * 60)

    print("\n[1] Buscando un bloque reciente...")
    height = fetch_text("https://mempool.space/api/blocks/tip/height")
    block_hash = fetch_text(f"https://mempool.space/api/block-height/{height}")
    
    print("[2] Descargando transacciones del bloque...")
    txids = fetch_json(f"https://mempool.space/api/block/{block_hash}/txids")
    
    target_txid = None
    tx_hex = None
    
    print("[3] Buscando una transaccion Legacy P2PKH (1 input, 1 output)...")
    for txid in txids[1:50]:
        try:
            tx = fetch_json(f"https://mempool.space/api/tx/{txid}")
            if not tx.get("vin") or not tx.get("vout"): continue
            if "scriptsig" not in tx["vin"][0]: continue
            if tx["vin"][0].get("witness"): continue
            if len(tx["vin"]) != 1 or len(tx["vout"]) != 1: continue
            
            # Es Legacy, 1 input, 1 output
            target_txid = txid
            tx_hex = fetch_text(f"https://mempool.space/api/tx/{txid}/hex")
            break
        except Exception:
            continue

    if not tx_hex:
        print("No se encontro una transaccion Legacy simple en las primeras 50.")
        return

    print(f"    Transaccion seleccionada: {target_txid}")
    
    tx_bytes = bytes.fromhex(tx_hex)
    
    # Parseo manual para transaccion con 1 input, 1 output
    offset = 4 # version
    n_inputs, offset = read_varint(tx_bytes, offset)
    if n_inputs != 1: return
    
    prev_txid = tx_bytes[offset:offset+32]
    offset += 32
    prev_vout = int.from_bytes(tx_bytes[offset:offset+4], 'little')
    offset += 4
    
    script_len, offset = read_varint(tx_bytes, offset)
    script_sig = tx_bytes[offset:offset+script_len]
    offset += script_len
    
    sequence = tx_bytes[offset:offset+4]
    offset += 4
    
    n_outputs, offset = read_varint(tx_bytes, offset)
    if n_outputs != 1: return
    
    value = tx_bytes[offset:offset+8]
    offset += 8
    
    out_script_len, offset = read_varint(tx_bytes, offset)
    out_script_pubkey = tx_bytes[offset:offset+out_script_len]
    offset += out_script_len
    
    locktime = tx_bytes[offset:offset+4]

    # Obtener el scriptPubKey del UTXO que se esta gastando
    prev_txid_hex = prev_txid[::-1].hex()
    prev_tx_data = fetch_json(f"https://mempool.space/api/tx/{prev_txid_hex}")
    script_pubkey = bytes.fromhex(prev_tx_data["vout"][prev_vout]["scriptpubkey"])
    
    # Extraer firma y pubkey del scriptSig
    sig_len = script_sig[0]
    sig_der = script_sig[1:1+sig_len-1]
    pubkey_len = script_sig[1+sig_len]
    pubkey_bytes = script_sig[2+sig_len:2+sig_len+pubkey_len]
    
    # Extraer R y S
    if sig_der[0] != 0x30: return
    r_len = sig_der[3]
    r = int.from_bytes(sig_der[4:4+r_len], 'big')
    s_len = sig_der[5+r_len]
    s = int.from_bytes(sig_der[6+r_len:6+r_len+s_len], 'big')
    
    # Reconstruir Sighash para 1 input, 1 output
    # Formato: version + n_inputs + [prev_txid + prev_vout + script_pubkey + sequence] + n_outputs + [value + script_pubkey] + locktime + sighash_type
    sighash_data = (
        tx_bytes[0:4] +  # version
        b'\x01' +  # n_inputs
        prev_txid +
        prev_vout.to_bytes(4, 'little') +
        bytes([len(script_pubkey)]) + script_pubkey +  # script_pubkey en lugar de scriptSig
        sequence +
        b'\x01' +  # n_outputs
        value +
        bytes([len(script_pubkey)]) + script_pubkey +
        locktime +
        b'\x01\x00\x00\x00'  # SIGHASH_ALL
    )
    
    sighash = sha256d(sighash_data)
    
    print("\n[4] Extrayendo datos criptograficos...")
    print(f"    Pubkey (hex): {pubkey_bytes.hex()[:20]}...")
    print(f"    Firma R: {hex(r)[:20]}...")
    print(f"    Firma S: {hex(s)[:20]}...")
    
    # Descomprimir pubkey
    if pubkey_bytes[0] in (2, 3):
        x = int.from_bytes(pubkey_bytes[1:33], 'big')
        y_sq = (pow(x, 3, P) + 7) % P
        y = pow(y_sq, (P + 1) // 4, P)
        if (y % 2) != (pubkey_bytes[0] % 2):
            y = P - y
        public_key = (x, y)
    else:
        x = int.from_bytes(pubkey_bytes[1:33], 'big')
        y = int.from_bytes(pubkey_bytes[33:65], 'big')
        public_key = (x, y)

    print("\n[5] Verificando firma ECDSA con matematica de curvas elipticas...")
    is_valid = verify_ecdsa(public_key, (r, s), sighash)
    
    print("\n" + "=" * 60)
    print("  RESULTADO")
    print("=" * 60)
    if is_valid:
        print("  ✅ FIRMA ECDSA VALIDA")
        print("     La transaccion fue firmada por el dueno de la llave privada.")
        print("     Los fondos estan autorizados a moverse.")
    else:
        print("  ❌ FIRMA ECDSA INVALIDA (o el parser fallo)")

if __name__ == "__main__":
    main()
