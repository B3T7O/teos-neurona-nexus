#!/usr/bin/env python3
"""
EXP-064: Centinela de Dominios (El Truco de Feynman)
Busca recursivamente la llave 'domains' en el JSON de AxeOS, sin importar
dónde esté anidada. Analiza el balance del ASIC y alerta si hay degradación.
"""
import json
import urllib.request
import statistics
import time
from datetime import datetime

BITAXE_IP = "192.168.18.45"

def find_domains_recursive(obj):
    """Truco de Feynman: busca 'domains' en cualquier nivel de profundidad."""
    if isinstance(obj, dict):
        if "domains" in obj and isinstance(obj["domains"], list) and len(obj["domains"]) == 4:
            return obj["domains"]
        for key, value in obj.items():
            result = find_domains_recursive(value)
            if result: return result
    elif isinstance(obj, list):
        for item in obj:
            result = find_domains_recursive(item)
            if result: return result
    return []

def check_domains():
    try:
        with urllib.request.urlopen(f"http://{BITAXE_IP}/api/system/info", timeout=10) as r:
            d = json.loads(r.read())
    except Exception as e:
        print(f"❌ Error conectando al Bitaxe: {e}")
        return

    domains = find_domains_recursive(d)
    
    if not domains:
        print("⚠️ El firmware no reportó dominios en esta lectura.")
        return

    total = sum(domains)
    mean = statistics.mean(domains)
    stdev = statistics.stdev(domains)
    cv = (stdev / mean) * 100 if mean > 0 else 0

    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] === 🕵️‍♂️ CENTINELA DE DOMINIOS ===")
    for i, val in enumerate(domains):
        alert = ""
        if val < mean * 0.80:
            alert = " 🔴 ¡ALERTA!"
        elif val < mean * 0.90:
            alert = " 🟡 Precaución"
        print(f"  Dominio {i}: {val:.2f} GH/s{alert}")
    
    print(f"  Total: {total:.2f} GH/s | Media: {mean:.2f} | CV: {cv:.2f}%")

    if cv > 15:
        print("  🔴 CRÍTICO: Un dominio está fallando (posible degradación de silicio).")
    elif cv > 8:
        print("  🟡 ADVERTENCIA: Dominios desbalanceados. Monitorear.")
    else:
        print("  ✅ SALUDABLE: Los 4 dominios están perfectamente balanceados.")

if __name__ == "__main__":
    check_domains()
