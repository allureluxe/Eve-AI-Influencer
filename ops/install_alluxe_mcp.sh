#!/usr/bin/env bash
set -euo pipefail

REPO="${ALLUXE_REPO:-/opt/Eve-AI-Influencer}"
ENV_DIR="/etc/alluxe"
ENV_FILE="${ENV_DIR}/mcp-tunnel.env"
SERVICE_SRC="${REPO}/systemd/alluxe-mcp-tunnel.service"
SERVICE_DST="/etc/systemd/system/alluxe-mcp-tunnel.service"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root." >&2
  exit 1
fi
if [[ ! -f "${REPO}/ops/mcp_alluxe.py" ]]; then
  echo "MCP bridge not found at ${REPO}/ops/mcp_alluxe.py" >&2
  exit 1
fi
if [[ ! -x /usr/local/bin/tunnel-client ]]; then
  echo "Install the latest OpenAI tunnel-client first." >&2
  exit 2
fi

install -d -m 0750 "${ENV_DIR}"
if [[ ! -f "${ENV_FILE}" ]]; then
  cat > "${ENV_FILE}" <<'EOF'
# Runtime key for OpenAI Secure MCP Tunnel. Never commit this file.
CONTROL_PLANE_API_KEY=
EOF
  chmod 0600 "${ENV_FILE}"
  echo "Created ${ENV_FILE}; put the tunnel runtime key in it and initialize the 'alluxe' profile."
  exit 3
fi

python3 -m py_compile "${REPO}/ops/mcp_alluxe.py"
install -m 0644 "${SERVICE_SRC}" "${SERVICE_DST}"
systemctl daemon-reload
systemctl enable alluxe-mcp-tunnel.service
systemctl restart alluxe-mcp-tunnel.service
echo "Alluxe MCP tunnel service installed."
systemctl --no-pager --full status alluxe-mcp-tunnel.service || true
