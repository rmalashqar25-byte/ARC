"""Server administrator: grant the private runner to one known browser workspace."""

import argparse
import hashlib
import json
import os
import uuid
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "session_uuid", help="UUID-v4 of the intended ARC browser workspace"
    )
    args = parser.parse_args()
    if os.name != "posix" or os.geteuid() != 0:
        parser.error("Run as root on the ARC server")
    try:
        session = uuid.UUID(args.session_uuid)
        if session.version != 4 or str(session) != args.session_uuid.lower():
            raise ValueError()
    except ValueError:
        parser.error("Expected an exact workspace UUID-v4")
    path = Path("/var/lib/arc/terminal/grants.json")
    state = json.loads(path.read_text())
    actor = "guest:" + hashlib.sha256(str(session).encode()).hexdigest()
    if state.get("actors") and state["actors"] != [actor]:
        parser.error(
            "Another workspace is already connected; revoke it explicitly first"
        )
    state.update(actors=[actor], paired=True)
    state.pop("pairing_hash", None)
    temporary = path.with_suffix(".new")
    temporary.write_text(json.dumps(state))
    os.chown(temporary, 10001, 10001)
    temporary.chmod(0o600)
    temporary.replace(path)
    print("The specified workspace can now use the isolated terminal.")


if __name__ == "__main__":
    main()
