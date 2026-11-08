#!/bin/bash
# Script para arrancar TEOS Neurona Nexus con setsid (evita huérfanos y duplicados).

# Candado: solo un start_teos.sh puede ejecutarse a la vez
exec 9>/tmp/teos_start.lock
flock -n 9 || { echo "⚠️  start_teos.sh ya está en ejecución. Ignorando."; exit 1; }

cd "$(dirname "$0")"

# Configurar IP del Bitaxe
export BITAXE_IP=192.168.18.45

# Matar cualquier proceso viejo
pkill -9 -f "core.collector" 2>/dev/null
pkill -9 -f "core.scheduler" 2>/dev/null
pkill -9 -f "web/server.py" 2>/dev/null
sleep 2

# Arrancar los 3 procesos con setsid (sesión independiente, no huérfanos)
echo "Arrancando colector..."
setsid python3 -u -m core.collector > logs/collector.log 2>&1 < /dev/null &

echo "Arrancando scheduler (incluye learning_loop)..."
setsid python3 -u -m core.scheduler > logs/scheduler.log 2>&1 < /dev/null &

echo "Arrancando servidor web..."
setsid python3 -u web/server.py > logs/web-server.log 2>&1 < /dev/null &

sleep 5

# Verificar
echo ""
echo "=== Procesos activos ==="
ps -eo pid,ppid,cmd | grep -E "core\.(collector|scheduler)|web/server" | grep -v grep

echo ""
echo "=== Web ==="
for i in 1 2 3 4 5; do
    code=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8765/)
    if [ "$code" = "200" ]; then
        echo "HTTP 200"
        break
    fi
    sleep 2
done
