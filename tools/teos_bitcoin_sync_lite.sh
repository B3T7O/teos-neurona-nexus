#!/usr/bin/env bash
set -u

DATA="$HOME/.bitcoin"
LOGDIR="$HOME/teos-neurona-nexus/logs"
LOG="$LOGDIR/teos_bitcoin_sync_lite.log"
MODE="${1:-once}"
INTERVAL="${2:-30}"

if [[ "$MODE" != "once" && "$MODE" != "--watch" ]]; then
    echo "Uso: $0 [once|--watch] [intervalo_segundos]"
    exit 2
fi

if [[ ! "$INTERVAL" =~ ^[0-9]+$ ]] || (( INTERVAL < 5 )); then
    echo "El intervalo debe ser de al menos 5 segundos."
    exit 2
fi

report() {
    echo
    echo "=================================================="
    echo " TEOS BITCOIN SYNC LITE v1 - SOLO LECTURA"
    date '+Fecha: %Y-%m-%d %H:%M:%S %Z'
    echo "=================================================="

    echo
    echo "--- Bitcoin Core ---"
    if pgrep -x bitcoind >/dev/null 2>&1; then
        ps -C bitcoind -o pid,stat,etime,pcpu,pmem,args
        echo
        echo "RPC blockchain:"
        local chain
        chain="$(timeout 4 bitcoin-cli -datadir="$DATA" getblockchaininfo 2>/dev/null || true)"
        if [[ -n "$chain" ]]; then
            printf '%s' "$chain" | python3 -c '
import json,sys
try:
 d=json.load(sys.stdin)
 for k in ("chain","blocks","headers","verificationprogress",
           "initialblockdownload","pruned","warnings"):
  print(f"{k}: {d.get(k, \"no disponible\")}")
except Exception:
 print("No se pudo interpretar la respuesta RPC")
'
        else
            echo "RPC no disponible; revisar estado y conexión local."
        fi

        echo
        echo "Red:"
        local net
        net="$(timeout 4 bitcoin-cli -datadir="$DATA" getnetworkinfo 2>/dev/null || true)"
        if [[ -n "$net" ]]; then
            printf '%s' "$net" | python3 -c '
import json,sys
try:
 d=json.load(sys.stdin)
 print("networkactive:",d.get("networkactive"))
 print("connections:",d.get("connections"))
 print("version:",d.get("subversion"))
except Exception:
 print("No se pudo interpretar la respuesta RPC")
'
        else
            echo "Información de red no disponible por RPC."
        fi
    else
        echo "DETENIDO: no se encontró bitcoind."
    fi

    echo
    echo "--- Recursos WSL ---"
    uptime
    free -h
    echo
    ps -eo pid,comm,pcpu,pmem --sort=-pcpu | head -n 8

    echo
    echo "--- NEURONA: solo observación ---"
    if pgrep -x python3 >/dev/null 2>&1; then
        ps -C python3 -o pid,stat,etime,pcpu,pmem,args --sort=-pcpu | head -n 6
    else
        echo "No se encontraron procesos python3."
    fi

    echo
    echo "--- Espacio de datos Bitcoin ---"
    du -sh "$DATA/blocks" "$DATA/chainstate" 2>/dev/null || true
    echo "Fin del informe."
}

if [[ "$MODE" == "--watch" ]]; then
    mkdir -p "$LOGDIR"
    echo "Monitor activo cada $INTERVAL segundos."
    echo "Registro: $LOG"
    echo "Para salir, pulsa Ctrl+C. No detiene procesos."
    while true; do
        report 2>&1 | tee -a "$LOG"
        sleep "$INTERVAL"
    done
else
    report
fi
