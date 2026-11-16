#!/usr/bin/env python3
"""
Proof of History: Valida que los nonces históricos coinciden con los nonces
reales de los bloques de Bitcoin, consultando mempool.space.
"""
import json
import urllib.request
import random
import time
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
NONCES_FILE = ROOT / "data" / "processed" / "nonces_10k.json"
OUTPUT_FILE = ROOT / "data" / "audit" / "proof_of_history.json"
API = "https://mempool.space/api"

def fetch_text(url):
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            return r.read().decode().strip()
    except Exception:
        return None

def fetch_json(url):
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            return json.loads(r.read())
    except Exception:
        return None

def verify_nonce(nonce_entry):
    height = nonce_entry.get("height")
    our_nonce = nonce_entry.get("nonce")
    
    if height is None or our_nonce is None:
        return None
    
    # 1. Obtener el hash del bloque (texto plano)
    block_hash = fetch_text(f"{API}/block-height/{height}")
    if not block_hash or len(block_hash) < 60:
        return {"error": "block_hash_failed", "height": height}
    
    # 2. Obtener la info del bloque (JSON con nonce incluido)
    block_info = fetch_json(f"{API}/block/{block_hash}")
    if not block_info or "nonce" not in block_info:
        return {"error": "block_info_failed", "height": height}
    
    block_nonce = block_info["nonce"]
    
    return {
        "height": height,
        "our_nonce": our_nonce,
        "block_nonce": block_nonce,
        "match": (our_nonce == block_nonce),
        "block_hash": block_hash
    }

def main():
    print("🔍 PROOF OF HISTORY - Validando nonces históricos...\n")
    
    if not NONCES_FILE.exists():
        print("❌ No se encontró nonces_10k.json")
        return
    
    with NONCES_FILE.open("r", encoding="utf-8") as f:
        all_nonces = json.load(f)
    
    print(f"📊 Total de nonces disponibles: {len(all_nonces):,}")
    
    valid_nonces = [n for n in all_nonces if n.get("height", 0) > 0]
    sample = random.sample(valid_nonces, min(30, len(valid_nonces)))
    
    print(f"🎲 Muestra aleatoria a validar: {len(sample)} nonces\n")
    
    results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_sample": len(sample),
        "verified": 0,
        "mismatched": 0,
        "errors": 0,
        "details": []
    }
    
    for i, nonce_entry in enumerate(sample, 1):
        print(f"  [{i}/{len(sample)}] Bloque #{nonce_entry.get('height')}...")
        result = verify_nonce(nonce_entry)
        
        if result is None:
            results["errors"] += 1
        elif "error" in result:
            results["errors"] += 1
            results["details"].append(result)
        elif result["match"]:
            results["verified"] += 1
            results["details"].append(result)
            print(f"      ✅ Match: {result['our_nonce']:,}")
        else:
            results["mismatched"] += 1
            results["details"].append(result)
            print(f"      ❌ Discrepancia: nuestro {result['our_nonce']:,} vs bloque {result['block_nonce']:,}")
        
        time.sleep(1.5)  # Pausa para evitar rate limits
    
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(results, indent=2), encoding="utf-8")
    
    print(f"\n{'='*60}")
    print(f"  📜 RESULTADOS DEL PROOF OF HISTORY")
    print(f"{'='*60}")
    print(f"  Total muestreados: {results['total_sample']}")
    print(f"  ✅ Verificados:     {results['verified']}")
    print(f"  ❌ Discrepancias:   {results['mismatched']}")
    print(f"  ⚠️  Errores:        {results['errors']}")
    print(f"\n  Reporte guardado en: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
