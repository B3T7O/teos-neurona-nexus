#!/usr/bin/env python3
"""Monitor pasivo de wallet: alerta si el balance cambia."""
import json, time, urllib.request
from pathlib import Path
from datetime import datetime

ADDR = "bc1q20m7sy4ks42yt67m44t3dc6tun387v5z6lykxt"
API = f"https://mempool.space/api/address/{ADDR}"
STATE = Path(__file__).resolve().parent.parent / "data" / "processed" / "wallet_state.json"
LOG = Path(__file__).resolve().parent.parent / "logs" / "wallet_monitor.log"

def fetch():
    with urllib.request.urlopen(API, timeout=15) as r:
        return json.loads(r.read())

def load_state():
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {"last_balance": 0, "last_check": None}

def save_state(s):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(s, indent=2))

def log(msg):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(f"[{datetime.now().isoformat()}] {msg}\n")
    print(msg, flush=True)

def main():
    log(f"Wallet monitor iniciado para {ADDR[:12]}...")
    state = load_state()
    while True:
        try:
            d = fetch()
            chain = d.get("chain_stats", {})
            mempool = d.get("mempool_stats", {})
            bal_chain = chain.get("funded_txo_sum", 0) - chain.get("spent_txo_sum", 0)
            bal_mempool = mempool.get("funded_txo_sum", 0) - mempool.get("spent_txo_sum", 0)
            total = bal_chain + bal_mempool
            if total != state.get("last_balance", 0):
                log(f"💰 CAMBIO DE BALANCE: {state.get('last_balance',0)} → {total} sats")
                log(f"   Confirmado: {bal_chain} sats | En mempool: {bal_mempool} sats")
                log(f"   ⚠️  ¡REVISA LA WALLET AHORA!")
                state["last_balance"] = total
                save_state(state)
            else:
                log(f"Sin cambios: {total} sats ({bal_chain} conf + {bal_mempool} mempool)")
            time.sleep(3600)  # 1 hora
        except Exception as e:
            log(f"ERROR: {e}")
            time.sleep(3600)

if __name__ == "__main__":
    main()
