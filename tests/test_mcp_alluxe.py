import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ops" / "mcp_alluxe.py"


class TestAlluxeMcp(unittest.TestCase):
    def run_rpc(self, payload):
        env = os.environ.copy()
        env.pop("SUPABASE_URL", None)
        env.pop("SUPABASE_SERVICE_KEY", None)
        p = subprocess.run(
            [sys.executable, str(SCRIPT)],
            input=json.dumps(payload) + "\n",
            text=True,
            capture_output=True,
            check=True,
            timeout=5,
            env=env,
        )
        return json.loads(p.stdout.strip())

    def test_initialize(self):
        r = self.run_rpc({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}},
        })
        self.assertEqual(r["result"]["serverInfo"]["name"], "alluxe-vps")

    def test_tools_list_is_safe(self):
        r = self.run_rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = {x["name"] for x in r["result"]["tools"]}
        self.assertEqual(names, {"alluxe_status", "alluxe_ask", "alluxe_recent"})
        self.assertNotIn("shell", names)
        self.assertNotIn("run_command", names)


if __name__ == "__main__":
    unittest.main()
