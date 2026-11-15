# EXP-043: Retiro Oficial de la Adaptación Controlada

**Fecha:** 2026-11-15
**Objetivo:** Documentar la obsolescencia y el retiro funcional de `core/controlled_adaptation.py`.

## Contexto
En las primeras fases del proyecto, `controlled_adaptation.py` era el mecanismo encargado de ajustar los parámetros del sistema en función de los errores de predicción (usando el archivo `learning_outcomes_v2.jsonl`).

## ¿Por qué se retira?
Tras la integración de las nuevas capas de IA y lógica, la Adaptación Controlada quedó **redundante**:
1.  **Rete Engine:** Ahora es el responsable de las decisiones de hardware (frecuencia, voltaje, ventilador) basadas en reglas deterministas.
2.  **Evolve Lab:** Optimiza los pesos del Meta Learner mediante algoritmos genéticos (APE 2.92%).
3.  **MLP Lite:** Predice con 10 sentidos (Regex, Shares, Stales, Duplicados, etc.).
4.  **Meta Learner:** Selecciona el mejor modelo dinámicamente.

## Verificación
Un `grep` en el código (`grep -rn "controlled_adaptation" core/`) confirma que **ningún módulo del sistema la invoca**. Solo se referencia a sí misma dentro de su propio archivo.

## Conclusión
El archivo `core/controlled_adaptation.py` se mantiene en el repositorio como referencia histórica, pero **no se ejecuta y no afecta al sistema actual**. El ecosistema TEOS Neurona Nexus está compuesto ahora por 4 cerebros especializados (Rete, Evolve, MLP Lite, Meta Learner) que han superado con creces su funcionalidad original.
