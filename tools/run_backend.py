"""Run ARC locally with the project's own environment, never the audit harness."""

import argparse
import os
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib/backend"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    from dotenv import load_dotenv

    # Explicit local launch: the project config wins over stale shell credentials.
    os.environ.pop("PYTHON_DOTENV_DISABLED", None)
    load_dotenv(ROOT / ".env", override=True)
    os.environ["PYTHON_DOTENV_DISABLED"] = "1"
    os.environ.setdefault("ARC_ENVIRONMENT", "development")
    os.environ["ARC_LOCAL_DEVELOPER"] = "1"
    os.environ.setdefault("ARC_TERMINAL_AUTO_CONNECT", "1")
    os.environ.setdefault("ARC_COMPANY_WORKER_ENABLED", "1")
    if not os.getenv("ARC_AGENT_WORKSPACE_ROOT", "").strip():
        workspace = ROOT / ".arc/runtime"
        workspace.mkdir(parents=True, exist_ok=True)
        os.environ["ARC_AGENT_WORKSPACE_ROOT"] = str(workspace)
    from company.provider_config import ceo_configuration

    configuration = ceo_configuration()
    print(f"ARC local backend: http://127.0.0.1:{args.port}", flush=True)
    print(
        f"CEO provider: {configuration['provider']}; model: {configuration['model']}",
        flush=True,
    )
    print(f"CEO configured: {configuration['configured']}", flush=True)
    import uvicorn
    from local_services import supervise

    stop = threading.Event()
    threading.Thread(target=supervise, args=(stop,), daemon=True).start()

    try:
        uvicorn.run(
            "app:app", host="127.0.0.1", port=args.port, workers=1, access_log=False
        )
    finally:
        stop.set()


if __name__ == "__main__":
    main()
