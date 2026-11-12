#!/usr/bin/env python3
"""
Verificador ECDSA usando python-bitcoinlib (estandar de la comunidad).
Verifica la firma de una transaccion real de Bitcoin sin parseos manuales.
"""
import json
import urllib.request
from bitcoin.core import CTransaction, CBlock
from bitcoin.core.script import CScript, OP_HASH160, OP_EQUAL, OP_CHECKSIG, OP_DUP
from bitcoin.core.scripteval import VerifyScript, SCRIPT_VERIFY_P2SH, SCRIPT_VERIFY_STRICTENC

API = "https://mempool.space/api"

def fetch(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return r.read().decode().strip()

def main():
    print("=" * 60)
    print("  VERIFICADOR ECDSA (python-bitcoinlib)")
    print("=" * 60)

    print("\n[1] Descargando bloque 100,000...")
    block_hash = fetch(f"{API}/block-height/100000")
    txids = json.loads(fetch(f"{API}/block/{block_hash}/txids"))
    
    target_txid = None
    for txid in txids[1:20]:
        tx_data = json.loads(fetch(f"{API}/tx/{txid}"))
        if (tx_data.get("vin") and len(tx_data["vin"]) == 1 and 
            len(tx_data["vout"]) == 1 and tx_data["vin"][0].get("scriptsig")):
            target_txid = txid
            break
            
    if not target_txid:
        print("No se encontro transaccion legacy simple.")
        return

    print(f"    Transaccion: {target_txid}")

    print("\n[2] Descargando hex de la transaccion y del UTXO...")
    tx_hex = fetch(f"{API}/tx/{target_txid}/hex")
    tx_data = json.loads(fetch(f"{API}/tx/{target_txid}"))
    prev_txid = tx_data["vin"][0]["txid"]
    prev_vout = tx_data["vin"][0]["vout"]
    prev_tx_hex = fetch(f"{API}/tx/{prev_txid}/hex")
    prev_tx_data = json.loads(fetch(f"{API}/tx/{prev_txid}"))
    prev_script_pubkey = bytes.fromhex(prev_tx_data["vout"][prev_vout]["scriptpubkey"])

    print("\n[3] Parseando transacciones...")
    tx = CTransaction.deserialize(bytes.fromhex(tx_hex))
    prev_tx = CTransaction.deserialize(bytes.fromhex(prev_tx_hex))

    print("\n[4] Verificando firma con las reglas de Bitcoin...")
    # Creamos el scriptPubKey del UTXO
    script_pubkey = CScript(prev_script_pubkey)
    
    # La entrada 0 de la transaccion actual
    txin = tx.vin[0]
    script_sig = txin.scriptSig
    
    # Verificamos que el script_sig resuelve el script_pubkey
    try:
        VerifyScript(script_sig, script_pubkey, tx, 0, (SCRIPT_VERIFY_P2SH,))
        print("\n" + "=" * 60)
        print("  ✅ FIRMA ECDSA VALIDA")
        print("     La firma criptografica es autentica.")
        print("     El dueno de la llave privada autorizo esta transaccion.")
        print("=" * 60)
    except Exception as e:
        print("\n" + "=" * 60)
        print("  ❌ FIRMA ECDSA INVALIDA")
        print(f"     Error: {e}")
        print("=" * 60)

if __name__ == "__main__":
    main()
