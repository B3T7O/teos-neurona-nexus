"""
TEOS Evolve Lab v1.0
====================
Genetic algorithm to find optimal weights for the 5 prediction methods.
Uses 72k+ historical outcomes to evaluate fitness.

Author: Luis Alberto Siguencia Andrade (B3T7O)
License: Apache 2.0
"""
import json
import random
import statistics
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
OUTCOMES = ROOT / "data" / "processed" / "learning_outcomes_v2.jsonl"
OUTPUT = ROOT / "data" / "processed" / "evolve_champion.json"

# Parámetros del algoritmo genético (Opción B)
POPULATION_SIZE = 100
GENERATIONS = 50
SURVIVORS = 20
MUTATION_RATE = 0.10
MUTATION_MAGNITUDE = 0.10
MAX_OUTCOMES = 200000  # limitar a 20k para velocidad (sigue siendo representativo)

METHODS = [
    "adaptativo_neurona",
    "referencia_10m",
    "referencia_1h",
    "media_ultimas_5",
    "ultimo_hashrate",
]


def load_outcomes():
    """Carga pares (predicción por método, actual) agrupados por target_timestamp."""
    by_target = {}
    with OUTCOMES.open("r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    # Usar los últimos MAX_OUTCOMES
    if len(lines) > MAX_OUTCOMES:
        lines = lines[-MAX_OUTCOMES:]

    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        try:
            o = json.loads(ln)
        except json.JSONDecodeError:
            continue
        target = o.get("target_timestamp")
        method = o.get("method")
        pred = o.get("predicted_hashRate_GHs")
        actual = o.get("actual_hashRate_GHs")
        if not target or not method or not isinstance(pred, (int, float)) or not isinstance(actual, (int, float)):
            continue
        if actual <= 0:
            continue
        by_target.setdefault(target, {"actual": actual, "preds": {}})
        by_target[target]["preds"][method] = pred

    # Solo targets con TODOS los métodos (para evaluar combinaciones completas)
    complete = []
    for target, data in by_target.items():
        if all(m in data["preds"] for m in METHODS):
            complete.append({
                "actual": data["actual"],
                "preds": data["preds"],
            })
    return complete


def random_weights():
    """Genera pesos aleatorios normalizados."""
    raw = [random.random() + 0.01 for _ in METHODS]
    total = sum(raw)
    return {m: r / total for m, r in zip(METHODS, raw)}


def fitness(individual, data):
    """Calcula el APE medio de una combinación de pesos."""
    apes = []
    for row in data:
        pred = 0.0
        for m in METHODS:
            pred += individual[m] * row["preds"][m]
        actual = row["actual"]
        ape = abs(pred - actual) / actual * 100
        apes.append(ape)
    return statistics.mean(apes)


def crossover(p1, p2):
    """Cruce de dos individuos: mezcla de pesos por método."""
    child = {}
    for m in METHODS:
        # Mezcla aleatoria
        alpha = random.random()
        child[m] = alpha * p1[m] + (1 - alpha) * p2[m]
    # Normalizar
    total = sum(child.values())
    for m in child:
        child[m] /= total
    return child


def mutate(individual):
    """Aplica mutación pequeña a algunos pesos."""
    new = dict(individual)
    for m in METHODS:
        if random.random() < MUTATION_RATE:
            delta = random.uniform(-MUTATION_MAGNITUDE, MUTATION_MAGNITUDE)
            new[m] = max(0.01, new[m] + delta)
    total = sum(new.values())
    for m in new:
        new[m] /= total
    return new


def main():
    print("🧬 TEOS Evolve Lab v1.0")
    print(f"   Población: {POPULATION_SIZE} | Generaciones: {GENERATIONS}")
    print()
    print("📂 Cargando outcomes históricos...")
    data = load_outcomes()
    print(f"   {len(data)} targets completos (con los 5 métodos)")
    print()

    if not data:
        print("❌ No hay suficientes datos completos. Abortando.")
        return

    print("🧬 Generación 0: creando población inicial...")
    population = [random_weights() for _ in range(POPULATION_SIZE)]

    best_overall = None
    best_fitness_overall = 999.0

    for gen in range(GENERATIONS):
        # Evaluar
        scored = []
        for ind in population:
            fit = fitness(ind, data)
            scored.append((fit, ind))

        scored.sort(key=lambda x: x[0])

        # Guardar el mejor global
        if scored[0][0] < best_fitness_overall:
            best_fitness_overall = scored[0][0]
            best_overall = dict(scored[0][1])

        if gen % 10 == 0 or gen == GENERATIONS - 1:
            print(f"   Gen {gen:3d} | Mejor APE: {scored[0][0]:.4f}% | Global: {best_fitness_overall:.4f}%")

        # Seleccionar los mejores
        survivors = [ind for (fit, ind) in scored[:SURVIVORS]]

        # Generar nueva población
        new_pop = list(survivors)  # elitismo
        while len(new_pop) < POPULATION_SIZE:
            p1 = random.choice(survivors)
            p2 = random.choice(survivors)
            child = crossover(p1, p2)
            child = mutate(child)
            new_pop.append(child)

        population = new_pop

    print()
    print("=" * 60)
    print(" 🏆 CAMPEÓN EVOLUTIVO")
    print("=" * 60)
    print(f"   APE medio (sobre {len(data)} targets): {best_fitness_overall:.4f}%")
    print()
    print("   Pesos óptimos:")
    for m in METHODS:
        print(f"     {m:25s} {best_overall[m]:.4f}")
    print()

    champion = {
        "version": "TEOS Evolve Lab v1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "generations": GENERATIONS,
        "population_size": POPULATION_SIZE,
        "targets_evaluated": len(data),
        "ape_mean": round(best_fitness_overall, 4),
        "weights": {m: round(best_overall[m], 4) for m in METHODS},
        "methodology": "Genetic algorithm with elitism, crossover, and mutation",
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(champion, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"💾 Guardado en: {OUTPUT}")


if __name__ == "__main__":
    main()
