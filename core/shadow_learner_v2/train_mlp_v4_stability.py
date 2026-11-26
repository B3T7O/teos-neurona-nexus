#!/usr/bin/env python3
"""
TEOS MLP Lite V4 - Predictive Stability Detector
Entrena un MLP usando ventanas de tiempo para predecir si el error
superará el 1.0% en los próximos 5 pasos.
"""
import json
import numpy as np
from pathlib import Path
from datetime import datetime, timezone

BASE = Path(__file__).resolve().parents[2]
DATA = BASE / "data/raw/bitaxe_samples.marked.jsonl"
OUT = BASE / "data/processed/shadow_learner_v4"
OUT.mkdir(parents=True, exist_ok=True)

# Features de telemetría (física del minero)
FEATURES = ["temp", "vrTemp", "fanrpm", "power", "frequency", "errorPercentage"]
WINDOW_SIZE = 5      # Mirar los últimos 5 registros
LOOKAHEAD = 5        # Predecir si fallará en los próximos 5 registros
MIN_IMPROVEMENT = 0.05

def load_data():
    samples = []
    with DATA.open() as f:
        for line in f:
            try:
                d = json.loads(line)
                if all(k in d for k in FEATURES):
                    samples.append(d)
            except: pass
    return samples

def build_sequences(samples):
    X, Y = [], []
    n = len(samples)
    for i in range(n - WINDOW_SIZE - LOOKAHEAD):
        # Construir ventana de entrada
        window = []
        for j in range(WINDOW_SIZE):
            row = [float(samples[i+j].get(f, 0)) for f in FEATURES]
            window.extend(row)
        
        # Construir etiqueta (Target)
        # ¿Hubo un error > 1.0% en los próximos LOOKAHEAD pasos?
        future_errors = [float(samples[i+WINDOW_SIZE+k].get("errorPercentage", 0)) for k in range(LOOKAHEAD)]
        target = 1.0 if max(future_errors) > 1.0 else 0.0
        
        X.append(window)
        Y.append(target)
    return np.array(X), np.array(Y)

def standardize(X_tr, X_va, X_te):
    m = X_tr.mean(axis=0)
    s = X_tr.std(axis=0)
    s[s < 1e-8] = 1.0
    return (X_tr - m) / s, (X_va - m) / s, (X_te - m) / s, m, s

def train_mlp(X, Y, hidden=12, epochs=300, lr=0.01):
    n, d = X.shape
    np.random.seed(42)
    W1 = np.random.randn(d, hidden) * 0.1
    b1 = np.zeros(hidden)
    W2 = np.random.randn(hidden, 1) * 0.1
    b2 = np.zeros(1)
    
    for _ in range(epochs):
        Z1 = X @ W1 + b1
        A1 = np.maximum(0, Z1)
        Z2 = A1 @ W2 + b2
        p = 1 / (1 + np.exp(-np.clip(Z2, -500, 500))) # Sigmoid
        
        dZ2 = (p - Y.reshape(-1, 1)) / n
        dW2 = A1.T @ dZ2
        db2 = dZ2.sum(axis=0)
        
        dA1 = dZ2 @ W2.T
        dZ1 = dA1 * (Z1 > 0)
        dW1 = X.T @ dZ1
        db1 = dZ1.sum(axis=0)
        
        W1 -= lr * dW1; b1 -= lr * db1
        W2 -= lr * dW2; b2 -= lr * db2
    return W1, b1, W2, b2

def evaluate(y_true, y_pred_probs):
    y_pred = (y_pred_probs > 0.5).astype(int)
    tp = ((y_pred == 1) & (y_true == 1)).sum()
    fp = ((y_pred == 1) & (y_true == 0)).sum()
    fn = ((y_pred == 0) & (y_true == 1)).sum()
    
    prec = tp / max(tp + fp, 1)
    rec = tp / max(tp + fn, 1)
    f1 = 2 * prec * rec / max(prec + rec, 1e-10)
    return prec, rec, f1

def main():
    print("=== TEOS MLP Lite V4 (Predictive Stability) ===")
    samples = load_data()
    print(f"Samples válidos: {len(samples)}")
    
    X, Y = build_sequences(samples)
    print(f"X shape: {X.shape}, Y shape: {Y.shape}")
    print(f"Porcentaje de eventos inestables: {Y.mean()*100:.2f}%")

    # Split temporal
    n = len(X)
    a, b = int(n*0.70), int(n*0.85)
    X_tr, X_va, X_te = X[:a], X[a:b], X[b:]
    Y_tr, Y_va, Y_te = Y[:a], Y[a:b], Y[b:]

    X_tr_s, X_va_s, X_te_s, m, s = standardize(X_tr, X_va, X_te)

    print("Entrenando red neuronal (esto puede tardar unos segundos)...")
    W1, b1, W2, b2 = train_mlp(X_tr_s, Y_tr)

    # Predicciones
    prob_va = 1 / (1 + np.exp(-np.clip(np.maximum(0, X_va_s @ W1 + b1) @ W2 + b2, -500, 500)))
    prob_te = 1 / (1 + np.exp(-np.clip(np.maximum(0, X_te_s @ W1 + b1) @ W2 + b2, -500, 500)))

    prec, rec, f1 = evaluate(Y_te, prob_te)
    
    # Baseline: Predecir "siempre 0" (nunca inestable)
    baseline_pred = np.zeros_like(Y_te)
    bp, br, bf1 = evaluate(Y_te, baseline_pred)

    print("\n--- RESULTADOS (Test Set) ---")
    print(f"Baseline (Siempre 0): Precision={bp:.3f}, Recall={br:.3f}, F1={bf1:.3f}")
    print(f"MLP V4:               Precision={prec:.3f}, Recall={rec:.3f}, F1={f1:.3f}")

    improvement = f1 - bf1
    print(f"\nMejora sobre baseline: {improvement*100:.2f}%")

    status = "ACCEPTED" if improvement > MIN_IMPROVEMENT else "REJECTED"
    print(f"Status final: {status}")

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "improvement": float(improvement),
        "metrics": {"precision": prec, "recall": rec, "f1": f1},
        "baseline": {"precision": bp, "recall": br, "f1": bf1}
    }
    (OUT / "stability_report.json").write_text(json.dumps(report, indent=2))

    if status == "ACCEPTED":
        model = {
            "W1": W1.tolist(), "b1": b1.tolist(),
            "W2": W2.tolist(), "b2": b2.tolist(),
            "scaler_mean": m.tolist(), "scaler_std": s.tolist(),
            "features": FEATURES, "window_size": WINDOW_SIZE
        }
        (BASE / "data/processed/stability_model.json").write_text(json.dumps(model, indent=2))
        print("✅ stability_model.json guardado. ¡Listo para integrarse!")
    else:
        print("❌ El modelo no superó al baseline. No se guardó.")

if __name__ == "__main__":
    main()
