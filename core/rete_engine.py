#!/usr/bin/env python3
# TEOS Neurona Nexus - Motor de Reglas Rete Lite
import json
import urllib.request
import argparse
from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent
RULES_FILE = BASE_DIR / "data" / "config" / "rules.json"
LOG_FILE = BASE_DIR / "data" / "processed" / "rete_decisions.jsonl"
BITAXE_IP = os.environ.get("BITAXE_IP", "192.168.18.45")
BASE_URL = f"http://{BITAXE_IP}"

def get_current_state():
    """Obtiene los datos actuales del Bitaxe."""
    with urllib.request.urlopen(f"{BASE_URL}/api/system/info", timeout=5) as r:
        return json.loads(r.read())

def evaluate_condition(state, key, op, value):
    """Evalúa una condición lógica simple."""
    current_val = state.get(key)
    if current_val is None:
        return False
    
    if op == "gte": return current_val >= value
    if op == "lte": return current_val <= value
    if op == "gt":  return current_val > value
    if op == "lt":  return current_val < value
    if op == "eq":  return current_val == value
    return False

def execute_action(action, apply_changes):
    """Ejecuta la acción en el hardware o la simula."""
    action_type = action.get("type")
    value = action.get("value")
    
    if not apply_changes:
        print(f"   [SIMULACIÓN] Se aplicaría: {action_type} -> {value}")
        return

    payload = {}
    if action_type == "set_frequency":
        payload = {"frequency": value}
    elif action_type == "set_fan":
        payload = {"minFanSpeed": value}
    elif action_type == "set_voltage":
        payload = {"coreVoltage": value}
    else:
        return

    req = urllib.request.Request(
        f"{BASE_URL}/api/system",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="PATCH"
    )
    with urllib.request.urlopen(req, timeout=5) as r:
        if r.status == 200:
            print(f"   ✅ ACCIÓN EJECUTADA: {action_type} -> {value}")

def run_rete(apply_changes=False):
    # 1. Cargar reglas
    if not RULES_FILE.exists():
        print("❌ No se encontró rules.json")
        return

    with RULES_FILE.open("r", encoding="utf-8") as f:
        rules = json.load(f)["rules"]

    # 2. Ordenar por prioridad (1 es la más alta)
    rules.sort(key=lambda x: x.get("priority", 99))

    # 3. Obtener estado actual
    try:
        state = get_current_state()
    except Exception as e:
        print(f"❌ Error conectando al Bitaxe: {e}")
        return

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Evaluando Reglas Rete...")
    print(f"   Datos: Temp={state.get('temp')}°C, VRM={state.get('vrTemp')}°C, Err={state.get('errorPercentage')}%")

    # 4. Evaluar reglas en orden
    for rule in rules:
        conditions = rule.get("conditions", {})
        matches = True
        
        for key, cond in conditions.items():
            if not evaluate_condition(state, key, cond["op"] if "op" in cond else list(cond.keys())[0], list(cond.values())[0]):
                matches = False
                break
        
        if matches:
            print(f"   ⚠️ Regla disparada: [{rule['id']}] {rule['description']}")
            execute_action(rule["action"], apply_changes)
            
            # Guardar en el log de decisiones
            if apply_changes:
                LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
                with LOG_FILE.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"timestamp": datetime.now().isoformat(), "rule": rule["id"], "action": rule["action"]}) + "\n")
            
            # Solo ejecutamos la regla de mayor prioridad (Forward Chaining)
            break
    else:
        print("   ✅ Ninguna regla se cumplió. Manteniendo configuración actual.")

if __name__ == "__main__":
    from datetime import datetime
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Aplicar cambios al hardware")
    args = parser.parse_args()
    run_rete(apply_changes=args.apply)
