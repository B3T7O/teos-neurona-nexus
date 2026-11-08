#!/bin/bash
# Script para arrancar TEOS Neurona Nexus manualmente.
# Uso: ./start_teos.sh

cd "$(dirname "$0")"

# Configurar IP del Bitaxe
export BITAXE_IP=192.168.18.45

# Matar cualquier proceso viejo
pkill -9 -f "core.collector" 2>/dev/null
pkill -9 -f "core.scheduler" 2>/dev/null
pkill -9 -f "web/server.py" 2>/dev/null
sleep 2

# Arrancar los 3 procesos en segundo plano
echo "Arrancando colector..."
nohup python3 -u -m core.collector > logs/collector.log 2>&1 &

echo "Arrancando scheduler (incluye learning_loop)..."
nohup python3 -u -m core.scheduler > logs/scheduler.log 2>&1 &

echo "Arrancando servidor web..."
nohup python3 -u web/server.py > logs/web-server.log 2>&1 &

sleep 3

# Verificar
echo ""
echo "=== Procesos activos ==="
ps -eo pid,ppid,cmd | grep -E "core\.(collector|scheduler)|web/server" | grep -v grep

echo ""
echo "=== Web ==="
curl -s -o /dev/null -w "HTTP %{http_code}\n" http://127.0.0.1:8765/
