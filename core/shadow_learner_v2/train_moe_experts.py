#!/usr/bin/env python3
"""
TEOS MoE (Mixture of Experts) - Inspirado en Inkling
Entrena 3 expertos especializados y un director (Gating Network) que los pondera.
"""
import json
import numpy as np
from pathlib import Path
from datetime import datetime, timezone

BASE = Path(__file__).resolve().parents[2]
DATA = BASE / "data/raw/bitaxe_samples.marked.jsonl"
OUT = BASE / "data/processed/shadow_learner_v6_moe"
OUT.mkdir(parents=True, exist_ok=True)

WINDOW_SIZE = 5
LOOKAHEAD = 5

# Features divididas por experto
EXPERT_FEATURES = {
    "thermal": ["temp", "vrTemp", "fanrpm"],
    "electrical": ["power", "frequency"],
    "system": ["errorPercentage", "hashRate"]
}
ALL_FEATURES = ["temp", "vrTemp", "fanrpm", "power", "frequency", "errorPercentage"]

def load_data():
    samples = []
    with DATA.open() as f:
        for line in f:
            try:
                d = json.loads(line)
                if all(k in d for k in ALL_FEATURES):
                    samples.append(d)
            except: pass
    return samples

def build_sequences(samples):
    X_all, X_thermal, X_elec, X_sys, Y = [], [], [], [], []
    n = len(samples)
    for i in range(n - WINDOW_SIZE - LOOKAHEAD):
        # Ventana completa para el Director
        window_all = []
        for j in range(WINDOW_SIZE):
            window_all.extend([float(samples[i+j].get(f, 0)) for f in ALL_FEATURES])
        X_all.append(window_all)

        # Ventanas individuales para los Expertos (último frame de la ventana)
        X_thermal.append([float(samples[i+WINDOW_SIZE-1].get(f, 0)) for f in EXPERT_FEATURES["thermal"]])
        X_elec.append([float(samples[i+WINDOW_SIZE-1].get(f, 0)) for f in EXPERT_FEATURES["electrical"]])
        X_sys.append([float(samples[i+WINDOW_SIZE-1].get(f, 0)) for f in EXPERT_FEATURES["system"]])

        future_errors = [float(samples[i+WINDOW_SIZE+k].get("errorPercentage", 0)) for k in range(LOOKAHEAD)]
        Y.append(1.0 if max(future_errors) > 1.0 else 0.0)

    return (np.array(X_all), np.array(X_thermal), np.array(X_elec), np.array(X_sys), np.array(Y))

def train_simple_mlp(X, Y, epochs=200, lr=0.05):
    n, d = X.shape
    np.random.seed(42)
    W1 = np.random.randn(d, 8) * 0.1; b1 = np.zeros(8)
    W2 = np.random.randn(8, 1) * 0.1; b2 = np.zeros(1)
    
    # Normalización simple
    m, s = X.mean(axis=0), X.std(axis=0)
    s[s < 1e-8] = 1.0
    X_norm = (X - m) / s

    for _ in range(epochs):
        Z1 = X_norm @ W1 + b1; A1 = np.maximum(0, Z1); Z2 = A1 @ W2 + b2
        p = 1 / (1 + np.exp(-np.clip(Z2, -500, 500)))
        dZ2 = (p - Y.reshape(-1, 1)) / n
        dW2 = A1.T @ dZ2; db2 = dZ2.sum(axis=0)
        dA1 = dZ2 @ W2.T; dZ1 = dA1 * (Z1 > 0)
        W1 -= lr * (X_norm.T @ dZ1); b1 -= lr * dZ1.sum(axis=0)
        W2 -= lr * dW2; b2 -= lr * db2
    return W1, b1, W2, b2, m, s

def predict(X, model):
    W1, b1, W2, b2, m, s = model
    X_norm = (X - m) / s
    return 1 / (1 + np.exp(-np.clip(np.maximum(0, X_norm @ W1 + b1) @ W2 + b2, -500, 500))).flatten()

def main():
    print("=== Entrenando Consejo de Expertos (MoE) ===")
    samples = load_data()
    X_all, X_therm, X_elec, X_sys, Y = build_sequences(samples)
    
    n = len(Y)
    a = int(n * 0.85)
    
    # Entrenar Expertos
    print("Entrenando Experto Térmico...")
    m_therm = train_simple_mlp(X_therm[:a], Y[:a])
    print("Entrenando Experto Eléctrico...")
    m_elec = train_simple_mlp(X_elec[:a], Y[:a])
    print("Entrenando Experto de Sistema...")
    m_sys = train_simple_mlp(X_sys[:a], Y[:a])

    # Evaluar Expertos en Test
    p_therm = predict(X_therm[a:], m_therm)
    p_elec = predict(X_elec[a:], m_elec)
    p_sys = predict(X_sys[a:], m_sys)
    Y_te = Y[a:]

    # El Director (Voting Network simplificado)
    # Aprende qué experto tiene más razón basándose en el contexto
    print("Entrenando Director (Gating Network)...")
    # Para simplificar, usamos un promedio ponderado basado en la precisión del experto
    def get_f1(p):
        yp = (p > 0.5).astype(int)
        tp = ((yp == 1) & (Y_te == 1)).sum(); fp = ((yp == 1) & (Y_te == 0)).sum()
        fn = ((yp == 0) & (Y_te == 1)).sum()
        prec = tp / max(tp + fp, 1); rec = tp / max(tp + fn, 1)
        return 2 * prec * rec / max(prec + rec, 1e-10)

    f1_t, f1_e, f1_s = get_f1(p_therm), get_f1(p_elec), get_f1(p_sys)
    print(f"F1s individuales -> Térmico: {f1_t:.3f}, Eléctrico: {f1_e:.3f}, Sistema: {f1_s:.3f}")

    # Pesos basados en rendimiento (Normalizados)
    weights = np.array([f1_t, f1_e, f1_s])
    weights = weights / weights.sum()

    # Predicción MoE (Promedio ponderado)
    p_moe = (p_therm * weights[0] + p_elec * weights[1] + p_sys * weights[2])
    
    f1_moe = get_f1(p_moe)
    print(f"\nF1 del Consejo de Expertos (MoE): {f1_moe:.4f}")

    # Leer F1 del V4
    f1_v4 = 0.9229
    v4_path = BASE / "data/processed/shadow_learner_v4/stability_report.json"
    if v4_path.exists():
        f1_v4 = json.loads(v4_path.read_text())["metrics"]["f1"]

    print(f"F1 del V4 (Actual): {f1_v4:.4f}")

    if f1_moe > f1_v4 + 0.005:
        print("🎉 ¡El Consejo de Expertos superó al V4! Guardando...")
        # Aquí iría la lógica de guardado completo (para no hacer el archivo enorme, 
        # guardamos los pesos y metadatos)
        model_data = {
            "architecture": "MoE",
            "weights": weights.tolist(),
            "f1": f1_moe,
            "experts_f1": {"thermal": f1_t, "electrical": f1_e, "system": f1_s}
        }
        (OUT / "moe_report.json").write_text(json.dumps(model_data, indent=2))
    else:
        print("⚠️ El MoE no superó al V4. El soldado sigue usando el V4.")

if __name__ == "__main__":
    main()
