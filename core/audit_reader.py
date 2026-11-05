"""Lector de resultados de la auditoría general TEOS. Solo lectura."""

def build_audit_summary():
    return {
        "ok": True,
        "title": "Auditoría general TEOS NEURONA NEXUS",
        "status": "COMPLETADA",
        "completed": 3,
        "total": 3,
        "read_only": True,
        "points": [
            {
                "id": 1,
                "name": "Integridad del historial",
                "status": "COMPLETADO",
                "total_lines": 9678,
                "valid_records": 9676,
                "invalid_records": 2,
                "null_bytes": 1245,
                "frozen_records_compared": 846,
                "frozen_fields_matched": 4,
                "chronology_anomalies": 2,
                "limitations": [
                    "Dos registros JSON dañados.",
                    "Dos anomalías cronológicas identificadas.",
                    "La copia congelada solo coincide en cuatro campos."
                ]
            },
            {
                "id": 2,
                "name": "Evaluación predictiva",
                "status": "COMPLETADO",
                "pairs_compared": 1543,
                "base": {
                    "mae_GHs": 24.360103,
                    "rmse_GHs": 30.688369
                },
                "online": {
                    "mae_GHs": 25.026084,
                    "rmse_GHs": 31.611640
                },
                "conclusion": "El modelo online obtuvo peores resultados.",
                "online_mode": "shadow",
                "limitations": [
                    "No existe mejora predictiva demostrada.",
                    "El aprendizaje online debe permanecer en modo sombra."
                ]
            },
            {
                "id": 3,
                "name": "Integración térmica y validación funcional",
                "status": "COMPLETADO CON LIMITACIONES",
                "tests_passed": 31,
                "tests_total": 31,
                "controller_records": 346,
                "write_attempts": 0,
                "thermal_simulations": 4,
                "limitations": [
                    "La lógica se verificó mediante simulación.",
                    "No se probó físicamente el Bitaxe bajo temperaturas críticas."
                ]
            }
        ],
        "source": "Resultados documentados de la auditoría general",
        "note": "Este lector presenta resultados existentes; no ejecuta pruebas ni modifica datos."
    }
