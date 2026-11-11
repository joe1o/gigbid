"""
conftest.py - pytest runs this before any test. We use it to set test-only settings
BEFORE our modules are imported (they read settings at import time).
"""

import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="gigbid-tests-")

os.environ.update({
    # GigSim: no random 503s, clients react instantly, every job visible, throwaway database
    "GIGSIM_ERROR_RATE": "0",
    "GIGSIM_REVEAL_SECONDS": "0",
    "GIGSIM_RELEASE_ALL": "true",
    "GIGSIM_DB_PATH": os.path.join(_tmp, "gigsim.sqlite"),
    # MCP servers: throwaway databases
    "MARKETPLACE_MCP_DB": os.path.join(_tmp, "marketplace_mcp.sqlite"),
    "WORKSPACE_DB": os.path.join(_tmp, "workspace.sqlite"),
    "MCP_DEFAULT_USER": "ml_engineer",
    "GIGBID_SCHEDULER": "0",        # no background scouting during tests
})
