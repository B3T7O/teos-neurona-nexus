#!/usr/bin/env python3
# TEOS Neurona Nexus - Parser de Logs con Regex
import re
import json

# Patrones Regex para los logs de AxeOS (Bitaxe)
PATTERNS = {
    # Busca líneas como: asic_result ID: gae40f5a00000ac80, ASIC nr: 0, Core: 123/10, ver: 20074000 Nonce 14E346F6 diff 1098.0 of 1000.0
    "asic_result": re.compile(r"asic_result ID:\s*([a-f0-9]+).*?Nonce\s*([A-F0-9]+)\s*diff\s*([\d\.]+)\s*of\s*([\d\.]+)"),
    
    # Busca líneas de temperatura: fan_controller Temp: 53.2C, SetPoint: 55.0C, Output: 51.3%
    "fan_controller": re.compile(r"fan_controller Temp:\s*([\d\.]+)C"),
    
    # Busca la respuesta del pool (Stratum)
    "stratum_api": re.compile(r"stratum_api rx: (\{.*\})")
}

def parse_line(line):
    """Recibe una línea de texto y devuelve un diccionario con los datos extraídos."""
    result = {"raw": line.strip(), "type": "unknown"}
    
    # 1. Verificar si es un Share (asic_result)
    match_asic = PATTERNS["asic_result"].search(line)
    if match_asic:
        result["type"] = "share"
        result["asic_id"] = match_asic.group(1)
        result["nonce"] = match_asic.group(2)
        result["difficulty_found"] = float(match_asic.group(3))
        result["difficulty_target"] = float(match_asic.group(4))
        return result
        
    # 2. Verificar si es telemetría del ventilador
    match_fan = PATTERNS["fan_controller"].search(line)
    if match_fan:
        result["type"] = "temperature"
        result["temp"] = float(match_fan.group(1))
        return result
        
    return result

if __name__ == "__main__":
    # Prueba rápida con una línea falsa
    test_line = "[21861104] asic_result ID: gae40f5a00000ac80, ASIC nr: 0, Core: 123/10, ver: 20074000 Nonce 14E346F6 diff 1098.0 of 1000.0"
    print("Probando Parser Regex...")
    print(json.dumps(parse_line(test_line), indent=2))
