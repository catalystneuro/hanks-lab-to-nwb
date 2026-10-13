"""Smoke test: confirm DataJoint can reach the local Spyglass MySQL container
(port 3307) and that the Spyglass schemas materialize.

Run from this directory inside the `spyglass-photometry` conda env:

    conda activate spyglass-photometry
    python check_connection.py

Critical ordering: dj.config.load(...) BEFORE importing any spyglass module. Spyglass
runs dj.schema(...) at import time and would otherwise connect with the global
~/.datajoint_config.json (or TLS defaults).
"""

from pathlib import Path

import datajoint as dj

CONF = Path(__file__).with_name("dj_local_conf.json")

dj.config.load(str(CONF))
dj.conn(use_tls=False)  # explicit; matches "database.use_tls": false in the conf

import spyglass.common as sgc  # noqa: E402  (must follow dj.config.load)

print("datajoint:", dj.__version__)
print("connection:", dj.conn())
print("\nspyglass.common.Lab.heading:\n", sgc.Lab.heading)
print("\nSpyglass schemas visible on the server:")
for name in sorted(n for n in dj.list_schemas() if n.startswith("common")):
    print("  -", name)
print("\nOK: DataJoint connected and Spyglass schemas are present.")
