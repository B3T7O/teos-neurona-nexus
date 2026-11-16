# TEOS Neurona Nexus 🧠⚡

**Autonomous AI telemetry, predictive analytics, and cryptographic auditing for open-source Bitcoin mining.**

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Status: Production](https://img.shields.io/badge/status-production--ready-brightgreen)]()
[![Crypto: Audited](https://img.shields.io/badge/crypto-Merkle%20%2B%20ECDSA-orange)]()

TEOS is a self-hosted, lightweight AI layer designed for individual Bitcoin miners (specifically tested on the **Bitaxe Gamma 602**). Running on consumer hardware (even 4GB of RAM), it transforms a standard miner into a self-healing, predictive, and cryptographically audited node.

---

## 🏆 Core Capabilities

*   **🧠 Multi-Model AI Ensemble:** Runs 7 parallel learners (Ridge regression, Moving Averages, Meta-learners) to predict hashrate with an **APE of ~2.2%**.
*   **🫀 Live Crypto ECG:** A real-time Canvas dashboard that draws the "heartbeat" of the Bitcoin network (Block times) and tracks difficulty adjustments.
*   **🔐 Cryptographic Auditing:** Independently recalculates Merkle Roots and verifies ECDSA signatures of live Bitcoin blocks using `python-bitcoinlib`.
*   **🛡️ Autonomous Resilience:** Features a "Black Box" (Critical Guardian) that rotates backups every 5 minutes and auto-restores corrupted data after power/internet loss. Includes an Auto-Healer for systemd services.
*   **📊 Crypto Lab:** On-chain analytics visualizing the SHA256 Avalanche Effect, 10,000 historical Nonces (proving entropy), and Fourier transforms of thermal noise.
*   **⚙️ Hardware Control:** Predictive thermal throttling. It reduces frequency *before* the ASIC reaches critical temperatures.

---

## 🏗️ Architecture

The system is built around a centralized `Scheduler` that orchestrates everything every 5 minutes.

1.  **Collector** -> Captures telemetry via Bitaxe API.
2.  **Scheduler** -> Runs the AI learners, updates the Crypto Lab, and manages backups.
3.  **Learners** -> `learning_loop_v2`, `ridge_live`, `meta_learner`, `best_of_both`, etc.
4.  **Dashboard** (`web/server.py` + HTML/JS) -> Serves the live frontend (port 8765).
5.  **Guardians** -> `auto_healer` (service recovery) & `critical_guardian` (data integrity).

*(All predictions and telemetry are logged to append-only JSONL files for reproducibility).*

---

## 🚀 Quick Start

TEOS is designed to be deployed in minutes.

```bash
# 1. Clone the repository
git clone https://github.com/B3T7O/teos-neurona-nexus.git
cd teos-neurona-nexus

# 2. Run the automated installer
bash install.sh

# 3. Start the services
python3 -u -m core.collector    # Captures Bitaxe data
python3 -u -m core.scheduler    # Runs AI & Crypto Lab
python3 -u web/server.py        # Starts dashboard at http://localhost:8765

