#!/usr/bin/env bash
# Finalisation unique et sûre de la migration vers Bitvavo.
# Le script prépare, teste et installe le service, mais ne le démarre jamais.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

bash prepare_bitvavo.sh
