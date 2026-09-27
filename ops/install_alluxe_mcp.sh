#!/usr/bin/env bash
set -euo pipefail

REPO="${ALLUXE_REPO:-/opt/Eve-AI-Influencer}"
ENV_DIR="/etc/alluxe"
ENV_FILE="${ENV_DIR}/mcp.env"
SERVICE_SRC="${REPO}/systemd/alluxe-mcp.service"
SERVICE_DST="/etc/systemd/system/alluxe-mcp.service"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root." >&2
  exit 1
fi

if [[ ! -f "${REPO}/ops/mcp_alluxe.py" ]]; then
  echo "MCP bridge not found at ${REPO}/ops/mcp_alluxe.py" >&2
  exit 1
fi

install -d -m 0750 "${ENV_DIR}"

if [[ ! -f "${ENV_FILE}" ]]; then
  cat > "${ENV_FILE}" <<'EOF'
# Fill these on the VPS. Never commit this file.
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
ALLUXE_MCP_POLL_SECONDS=1
ALLUXE_MCP_TIMEOUT_SECONDS=120
EOF
  chmod 0600 "${ENV_FILE}"
  echo "Created ${ENV_FILE}; fill Supabase values, then rerun this installer."
  exit 2
fi

python3 -m py_compile "${REPO}/ops/mcp_alluxe.py"
install -m 0644 "${SERVICE_SRC}" "${SERVICE_DST}"
systemctl daemon-reload
systemctl enable alluxe-mcp.service
systemctl restart alluxe-mcp.service

echo "Alluxe MCP service installed."
systemctl --no-pager --full status alluxe-mcp.service || true
