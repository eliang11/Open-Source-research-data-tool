#!/bin/sh
# Seed the settings file on first run, so downloads land on the /data volume
# instead of inside the container where they would be lost.
#
# Only writes if the file is absent, so a mounted /config keeps its settings
# and anything changed in the Settings tab survives a restart.
set -e

python - <<'PYTHON'
import json
import os
import pathlib

config = pathlib.Path(os.environ.get("HOME", "/config")) / ".publicdataconfig.json"
if not config.exists():
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(
        json.dumps(
            {
                "download_dir": "/data",
                # Portals see this in the User-Agent. Set OPENDATA_CONTACT to
                # your email so operators can reach you if something looks off.
                "user_contact": os.environ.get("OPENDATA_CONTACT", "unknown-user"),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print("Created %s (downloads -> /data)" % config)
PYTHON

exec "$@"
