# Copyright (c) 2026 Luis Alberto Siguencia Andrade (B3T7O)
# SPDX-License-Identifier: Apache-2.0
#
# TEOS Neurona Nexus - Reference Implementation
# https://github.com/[TU_USUARIO]/teos-neurona-nexus

"""Ejecuta análisis periódicos sin intervenir en el colector Bitaxe."""

import time
import traceback
from datetime import datetime
from core.analyzer import analyze
from core.prospective_eval import main as evaluate_prospective
from core.learning_loop_v2 import main as run_learning_loop_v2
from core.neurona_ridge_live import main as run_ridge_live
from core.bitaxe_control import main as run_bitaxe_control

INTERVAL = 300  # 5 minutos


def main():
    print("TEOS NEURONA NEXUS: programador de análisis")
    print("Intervalo: 5 minutos. Detener con Ctrl+C.")

    try:
        while True:
            started = time.monotonic()
            print(f"\n[{datetime.now().astimezone().isoformat()}] Iniciando análisis")

            try:
                analyze()
            except Exception:
                print("Error durante el análisis:")
                traceback.print_exc()

            try:
                run_learning_loop_v2()
            except Exception:
                print("Error en el ciclo de aprendizaje V2; el programador continuará:")
                traceback.print_exc()

            try:
                run_ridge_live()
            except Exception:
                print("Error en el ciclo Ridge experimental; el programador continuará:")
                traceback.print_exc()
            try:
                run_bitaxe_control()
            except Exception:
                print("Error en la comprobación Bitaxe (sin aplicar cambios):")
                traceback.print_exc()

            try:
                evaluate_prospective()
            except Exception:
                print("Error en la evaluación prospectiva; el programador continuará:")
                traceback.print_exc()

            # === TEOS MetaLearner Lite v1 (shadow mode) ===
            try:
                from core.meta_learner_lite import compute_recommendation
                compute_recommendation()
            except Exception:
                pass  # Si falla, el scheduler sigue funcionando
            # =============================================

            # === TEOS Ensemble Learner v2-B (shadow mode) ===
            try:
                from core.ensemble_learner import compute_ensemble
                compute_ensemble()
            except Exception:
                pass
            # ================================================
            elapsed = time.monotonic() - started
            time.sleep(max(0, INTERVAL - elapsed))

    except KeyboardInterrupt:
        print("\nProgramador detenido. Historial conservado.")


if __name__ == "__main__":
    main()
