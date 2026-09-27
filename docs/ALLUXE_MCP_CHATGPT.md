# Alluxe ↔ ChatGPT via Secure MCP Tunnel

This bridge connects ChatGPT to the **existing** Alluxe master agent. It does
not create a second agent and it does not expose a shell.

## Architecture

ChatGPT → OpenAI Secure MCP Tunnel → `ops/mcp_alluxe.py` → Supabase
`alluxe_agent_messages` → existing `ops/agent_alluxe.py`.

The existing Alluxe agent keeps its current tools, guardrails and its ability
to consult OpenAI/Claude. The MCP layer only transports requests and answers.

## VPS installation

On the VPS, from the repository:

    sudo ops/install_alluxe_mcp.sh

The installer creates:

    /etc/alluxe/mcp.env

Put the existing VPS values for `SUPABASE_URL` and `SUPABASE_SERVICE_KEY`
there. Do not commit this file.

The service is:

    alluxe-mcp.service

## OpenAI Secure MCP Tunnel

OpenAI's current Secure MCP Tunnel is outbound-only: the VPS does not need an
inbound firewall port. The tunnel client reaches OpenAI over outbound HTTPS
and forwards MCP calls to the private server. See:

https://developers.openai.com/api/docs/guides/secure-mcp-tunnels

The current OpenAI setup requires a `tunnel_id` and a runtime API key for
`tunnel-client`. Create/manage the tunnel in Platform tunnel settings,
then configure the tunnel client to run this stdio server:

    python3 /opt/Eve-AI-Influencer/ops/mcp_alluxe.py

Do not put the runtime key or tunnel ID in Git.

## ChatGPT connection

In a ChatGPT workspace with developer mode enabled, create a developer-mode
app, choose **Tunnel**, and select/paste the tunnel ID. Then review the
discovered tools.

The OpenAI documentation says tunnel visibility depends on associating the
tunnel with the target ChatGPT workspace and having tunnel Read + Use
permissions.

## Security

The MCP intentionally exposes only:
- `alluxe_status`
- `alluxe_ask`
- `alluxe_recent`

It does not expose arbitrary shell execution, .env reading, git force push,
trading controls, or secret retrieval. Any action requested through
`alluxe_ask` is still executed by the existing Alluxe agent and therefore
remains subject to that agent's own guardrails.

## Verification

Before connecting ChatGPT, verify:

    python3 -m py_compile ops/mcp_alluxe.py
    python3 -m unittest tests/test_mcp_alluxe.py

Then verify the systemd service and the tunnel client. Do not claim the
ChatGPT connection is complete until ChatGPT can discover and call
`alluxe_status`.
