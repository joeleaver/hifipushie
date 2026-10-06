"""mcp.py: the hair tools called as an MCP client would (server.* functions directly)."""
import os, sys
from hifipushie import server
HR = os.environ["HR"]
r = server.look_hair("hs_tess", views=["three_quarter", "back"], size=320, clay=False, tier="main", debug="layers",
                     save=f"{HR}/ht_t_mcp_layers.png")
print(r[-1][:600])
if len(sys.argv) > 1:
    r = server.export_hair("hs_tess", sys.argv[1], tiers=["main"], groom=True, check=True, save=f"{HR}/ht_t_mcp_export.png")
    print(r[-1])
