# Contributing to TEOS Neurona Nexus

Thank you for your interest in contributing! This project aims to democratize AI
for individual Bitcoin miners, and community help is always welcome.

## Code of Conduct

- Be respectful and constructive.
- Focus on the technical merits of a proposal, not on the person.
- Assume good faith.
- Help others learn.

## How to Contribute

### 1. Reporting Bugs

- Open a [GitHub Issue](https://github.com/B3T7O/teos-neurona-nexus/issues) with a clear title and steps to reproduce.
- Include the output of `python3 tools/teos_audit.py --tail 500 --no-save`.
- Include your environment: OS, WSL version (if applicable), Python version, Bitaxe model.

### 2. Suggesting Features

- Open an Issue with the `enhancement` label.
- Explain the problem you want to solve, not just the solution.
- If possible, include a small proof-of-concept or reference link.

### 3. Submitting Code

1. Fork the repository.
2. Create a feature branch: `git checkout -b feat/your-feature-name`.
3. Make sure your commits are GPG-signed (`git commit -S`).
4. Write tests for new functionality.
5. Run `python3 tools/teos_audit.py --tail 500` and ensure the verdict is SANO or ADVERTENCIA.
6. Open a Pull Request describing what you changed, why, how you tested it, and any breaking changes.

### 4. Documentation

- Typos, clarifications, and examples are always welcome.
- If you find an outdated section, please open an Issue or PR.

## Development Setup

    git clone https://github.com/B3T7O/teos-neurona-nexus.git
    cd teos-neurona-nexus
    export BITAXE_IP=192.168.1.100   # your miner's LAN IP
    ./start_teos.sh
    xdg-open http://127.0.0.1:8765/

## Coding Standards

- **Language:** Python 3.12+.
- **Style:** PEP 8. Use black and ruff if available.
- **Type hints:** Prefer them for new functions.
- **No external dependencies** for core modules (use stdlib when possible).
- **Read-only by default:** Any module that touches the Bitaxe must have a dry-run mode.
- **Safety policy:** The controller must never increase frequency or voltage automatically.

## Security

- Report vulnerabilities privately to teos.neurona@proton.me (see `SECURITY.md`).
- Do not open public issues for security bugs.
- Never commit API keys, tokens, or wallet addresses.

## Questions?

Open a GitHub Issue or reach out via Telegram [@B3T7O](https://t.me/B3T7O).

Thank you for helping TEOS Neurona Nexus grow.
