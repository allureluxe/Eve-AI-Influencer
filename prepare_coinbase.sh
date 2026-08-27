#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

python3 -m pip install -r requirements.txt

cat <<'EOF'

============================================================
COINBASE — CONFIGURATION FINALE
============================================================
Ajoute uniquement ces 2 variables dans le .env du VPS :

COINBASE_API_KEY=<nom complet de la cle CDP Coinbase>
COINBASE_API_SECRET=<cle privee Coinbase, avec les \n conserves>

Optionnel :
COINBASE_QUOTE_ASSET=USD
COINBASE_DRY_RUN=1

Puis lance :
    python3 verifier_coinbase.py

Le verifier ne place AUCUN ordre. Quand il affiche
"RESULTAT : COINBASE PRETE", le branchement API est valide.
Pour passer ensuite en reel, le moteur reprend le dry_run general
du bot ; il n'y a pas de cle a remettre ailleurs.
============================================================
EOF
