#!/usr/bin/env python3
"""
Verificador de firma ECDSA usando la libreria `ecdsa` (estandar de Python).
Usa una transaccion legacy historica de Bitcoin hardcodeada.
"""
import hashlib
import ecdsa

# Transaccion historica: primer gasto de la direccion de Satoshi? No, es una legacy simple
# Vamos a usar los datos de una transaccion P2PKH verificada del bloque antiguo
# Datos extraidos de mempool.space de la tx: 6f7cf9580f1c2dfb3c4d5e6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c
# Pero para asegurar, vamos a usar la transaccion real del bloque 100,000 (legacy pura)

# En lugar de hardcodear, vamos a descargar una transaccion legacy REAL y verificarla
# usando la API de mempool.space pero pidiendole los datos limpios

import json
import urllib.request

API = "https://mempool.space/api"

def fetch_json(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read())

def fetch_text(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return r.read().decode().strip()

def sha256d(data: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()

def main():
    print("=" * 60)
    print("  VERIFICADOR ECDSA - CON LIBRERIA ESTANDAR")
    print("=" * 60)

    print("\n[1] Descargando una transaccion legacy desde mempool.space...")
    # Usamos una transaccion del bloque 100,000 (muy antigua, pre-SegWit seguro)
    block_hash = fetch_text(f"{API}/block-height/100000")
    txids = fetch_json(f"{API}/block/{block_hash}/txids")
    
    # Buscar una transaccion legacy simple
    target = None
    for txid in txids[1:30]:
        try:
            tx = fetch_json(f"{API}/tx/{txid}")
            if not tx.get("vin") or not tx.get("vout"): continue
            if len(tx["vin"]) != 1 or len(tx["vout"]) != 1: continue
            
            # Verificar que sea legacy P2PKH
            script_sig = tx["vin"][0].get("scriptsig", "")
            if not script_sig: continue
            if tx["vin"][0].get("witness"): continue
            
            # Obtener el hex
            tx_hex = fetch_text(f"{API}/tx/{txid}/hex")
            
            # Obtener el scriptPubKey del UTXO gastado
            prev_txid = tx["vin"][0]["txid"]
            prev_vout = tx["vin"][0]["vout"]
            prev_tx = fetch_json(f"{API}/tx/{prev_txid}")
            if prev_vout >= len(prev_tx["vout"]): continue
            spk = prev_tx["vout"][prev_vout]["scriptpubkey"]
            if not spk.startswith("76a914"): continue  # P2PKH solo
            
            target = {
                "txid": txid,
                "tx_hex": tx_hex,
                "script_pubkey": spk,
                "script_sig": script_sig,
            }
            break
        except Exception:
            continue

    if not target:
        print("No se encontro transaccion P2PKH legacy en el bloque 100,000")
        return

    print(f"    Transaccion: {target['txid']}")
    print(f"    script_pubkey: {target['script_pubkey']}")
    print(f"    script_sig: {target['script_sig'][:40]}...")

    # Parsear el scriptSig: [sig_len][sig][pubkey_len][pubkey]
    sig_script = bytes.fromhex(target["script_sig"])
    sig_len = sig_script[0]
    sig_der = sig_script[1:1+sig_len-1]  # sin el byte de sighash
    pubkey_len = sig_script[1+sig_len]
    pubkey_bytes = sig_script[2+sig_len:2+sig_len+pubkey_len]

    print(f"\n[2] Datos extraidos:")
    print(f"    Pubkey: {pubkey_bytes.hex()[:20]}...")
    print(f"    Firma (DER): {sig_der.hex()[:20]}...")

    # Reconstruir el sighash correctamente
    # Formato legacy: version + n_inputs + [prev_txid + prev_vout + script_pubkey + sequence] + n_outputs + [value + out_script] + locktime + sighash_type
    tx = fetch_json(f"{API}/tx/{target['txid']}")
    prev_tx = fetch_json(f"{API}/tx/{tx['vin'][0]['txid']}")
    
    prev_txid_bytes = bytes.fromhex(tx["vin"][0]["txid"])[::-1]
    prev_vout_bytes = tx["vin"][0]["vout"].to_bytes(4, "little")
    script_pubkey_bytes = bytes.fromhex(target["script_pubkey"])
    sequence_bytes = bytes.fromhex(tx["vin"][0]["sequence"]) if isinstance(tx["vin"][0]["sequence"], str) else tx["vin"][0]["sequence"].to_bytes(4, "little")
    
    # Output
    vout = tx["vout"][0]
    value_bytes = int(vout["value"]).to_bytes(8, "little")
    out_script = bytes.fromhex(vout["scriptpubkey"])
    
    locktime_bytes = tx["locktime"].to_bytes(4, "little")
    
    sighash_data = (
        int(tx["version"]).to_bytes(4, "little") +
        b"\x01" +
        prev_txid_bytes +
        prev_vout_bytes +
        bytes([len(script_pubkey_bytes)]) + script_pubkey_bytes +
        sequence_bytes +
        b"\x01" +
        value_bytes +
        bytes([len(out_script)]) + out_script +
        locktime_bytes +
        b"\x01\x00\x00\x00"
    )
    
    sighash = sha256d(sighash_data)
    print(f"\n[3] Sighash calculado: {sighash.hex()[:40]}...")

    # Verificar con la libreria ecdsa
    print("\n[4] Verificando firma con libreria ecdsa...")
    # Si la llave es sin comprimir (empieza con 04), quitamos el 04 para la libreria
    if len(pubkey_bytes) == 65 and pubkey_bytes[0] == 4:
        pubkey_str = pubkey_bytes[1:]
    else:
        pubkey_str = pubkey_bytes
        
    vk = ecdsa.VerifyingKey.from_string(pubkey_str, curve=ecdsa.SECP256k1)
    
    try:
        # Usamos sigdecode_der porque Bitcoin codifica las firmas en formato DER
        vk.verify(sig_der, sighash, sigdecode=ecdsa.util.sigdecode_der)
        print("\n" + "=" * 60)
        print("  ✅ FIRMA ECDSA VALIDA")
        print("     La firma criptografica es autentica.")
        print("     El dueno de la llave privada autorizo esta transaccion.")
        print("=" * 60)
    except ecdsa.BadSignatureError:
        print("\n" + "=" * 60)
        print("  ❌ FIRMA ECDSA INVALIDA")
        print("=" * 60)

if __name__ == "__main__":
    main()
