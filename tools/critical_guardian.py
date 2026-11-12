#!/usr/bin/env python3
"""
Guardián de Datos Críticos.
1. Hace un backup rápido de los JSONL críticos.
2. Verifica si los archivos actuales están corruptos y los restaura si es necesario.
"""
import os
import shutil
import json
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
DATA_PROC = ROOT / "data" / "processed"
DATA_EVOLVE = ROOT / "data" / "evolve"
BACKUP_DIR = ROOT / "data" / "critical_backups"

CRITICAL_FILES = [
    DATA_PROC / "learning_outcomes_v2.jsonl",
    DATA_PROC / "evolve_champion.json",
    DATA_EVOLVE / "history.jsonl"
]

def make_backup():
    """Crea una copia rápida de los archivos críticos."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    current_backup = BACKUP_DIR / f"backup_{timestamp}"
    current_backup.mkdir()
    
    for f in CRITICAL_FILES:
        if f.exists() and f.stat().st_size > 0:
            shutil.copy2(f, current_backup / f.name)
            
    # Mantener solo los últimos 5 backups para no llenar el disco
    backups = sorted(BACKUP_DIR.glob("backup_*"))
    if len(backups) > 5:
        for old in backups[:-5]:
            shutil.rmtree(old, ignore_errors=True)
            
    print(f"✅ Backup crítico guardado en: {current_backup.name}")

def is_valid_json_file(f):
    """Valida un archivo JSON o JSONL."""
    if f.suffix == '.json':
        try:
            with f.open('r', encoding='utf-8') as file:
                json.load(file)
            return True
        except Exception:
            return False
    elif f.suffix == '.jsonl':
        try:
            with f.open('rb') as file:
                file.seek(max(0, f.stat().st_size - 2000))
                lines = file.read().decode('utf-8', errors='ignore').strip().split('\n')
                if lines:
                    json.loads(lines[-1])
            return True
        except Exception:
            return False
    return True

def check_and_restore():
    """Verifica si los archivos actuales están corruptos y busca el mejor backup."""
    restored = False
    for f in CRITICAL_FILES:
        if not f.exists() or f.stat().st_size == 0:
            print(f"⚠️ Archivo faltante o vacío: {f.name}. Buscando backup...")
            restore_file(f)
            restored = True
        elif not is_valid_json_file(f):
            print(f"⚠️ Archivo corrupto detectado: {f.name}. Restaurando backup...")
            restore_file(f)
            restored = True
                
    if restored:
        print("🔄 Restauración completada. Los datos críticos están a salvo.")
    else:
        print("✅ Todos los archivos críticos están sanos.")

def restore_file(target_file):
    """Busca el backup más reciente y lo restaura."""
    backups = sorted(BACKUP_DIR.glob("backup_*"), reverse=True)
    for backup in backups:
        candidate = backup / target_file.name
        if candidate.exists() and candidate.stat().st_size > 0:
            shutil.copy2(candidate, target_file)
            print(f"  -> Restaurado {target_file.name} desde {backup.name}")
            return
    print(f"  -> ❌ No se encontró backup para {target_file.name}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "restore":
        check_and_restore()
    else:
        make_backup()
