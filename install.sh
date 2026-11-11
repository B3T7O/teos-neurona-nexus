#!/bin/bash
# TEOS Neurona Nexus - Instalador
# Uso: bash install.sh
# Requiere: Python 3.10+, git, curl

set -e

REPO_URL="https://github.com/B3T7O/teos-neurona-nexus.git"
INSTALL_DIR="${TEOS_DIR:-$HOME/teos-neurona-nexus}"

echo "=== TEOS Neurona Nexus - Instalador ==="
echo ""

# 1. Verificar Python
if ! command -v python3 &>/dev/null; then
    echo "ERROR: Python 3 no está instalado."
    echo "  Ubuntu/Debian: sudo apt install python3 python3-pip"
    echo "  macOS: brew install python3"
    exit 1
fi
PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "Python detectado: $PY_VER"

# 2. Clonar o actualizar
if [ -d "$INSTALL_DIR/.git" ]; then
    echo "Directorio ya existe. Actualizando..."
    cd "$INSTALL_DIR" && git pull
else
    echo "Clonando desde $REPO_URL ..."
    git clone "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# 3. Instalar dependencias
echo ""
echo "Instalando dependencias..."
python3 -m pip install --user --quiet numpy
echo "Dependencias instaladas."

# 4. Crear estructura de datos
mkdir -p data/raw data/processed data/healer data/evolve data/audit data/guardian logs
echo "Estructura de directorios creada."

# 5. Configurar BITAXE_IP
BITAXE_IP="${BITAXE_IP:-192.168.1.100}"
echo ""
echo "Bitaxe IP: $BITAXE_IP (puedes cambiarla editando core/collector.py)"
echo "  Actualmente en: $(grep -m1 'BITAXE_IP' core/collector.py || echo 'no encontrada')"

# 6. Verificar que el código corre
echo ""
echo "Verificando que el código compila..."
python3 -c "import ast; ast.parse(open('core/collector.py').read()); print('OK: sintaxis válida')"

# 7. Instrucciones finales
echo ""
echo "=== INSTALACIÓN COMPLETA ==="
echo ""
echo "Para arrancar manualmente:"
echo "  cd $INSTALL_DIR"
echo "  python3 -u -m core.collector    # capturar Bitaxe"
echo "  python3 -u -m core.scheduler    # learning loop cada 5 min"
echo "  python3 -u web/server.py        # dashboard en http://localhost:8765"
echo ""
echo "Para instalarlo como servicio systemd (recomendado):"
echo "  sudo cp systemd/*.service /etc/systemd/system/"
echo "  sudo systemctl daemon-reload"
echo "  sudo systemctl enable --now teos-nexus-collector teos-neurona-scheduler teos-neurona-api"
echo ""
echo "Para el auto-healer:"
echo "  nohup python3 -u tools/auto_healer.py --execute > logs/healer.log 2>&1 &"
echo ""
echo "Para el evolve-runner:"
echo "  nohup python3 -u tools/evolve_runner.py --execute > logs/evolve.log 2>&1 &"
echo ""
echo "Dashboard: http://localhost:8765"
echo "Logs: $INSTALL_DIR/logs/"
