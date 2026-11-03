"""Build and serve ARC locally in release mode without a debug compiler."""

import argparse
import shutil
import subprocess
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / ".arc/web"


class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self' 'wasm-unsafe-eval' https://www.gstatic.com; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
            "font-src 'self' data: https://fonts.gstatic.com; "
            "connect-src 'self' http://127.0.0.1:8765 https://www.gstatic.com https://fonts.gstatic.com; "
            "worker-src 'self' blob:; frame-ancestors 'none'; object-src 'none'; base-uri 'self'",
        )
        # Revalidate app files after a rebuild instead of retaining an old loader.
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", action="store_true", help="Build before serving")
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    if args.build:
        flutter = shutil.which("flutter")
        if not flutter:
            parser.error("Add the Flutter SDK bin directory to PATH first.")
        subprocess.run(
            [
                flutter,
                "build",
                "web",
                "--release",
                "--no-web-resources-cdn",
                "--dart-define=ARC_API_BASE_URL=http://127.0.0.1:8765",
                f"--output={OUTPUT}",
            ],
            cwd=ROOT,
            check=True,
        )
    if not (OUTPUT / "index.html").is_file():
        parser.error("No web build found. Run with --build first.")
    print(f"ARC: http://127.0.0.1:{args.port}", flush=True)
    server = ThreadingHTTPServer(
        ("127.0.0.1", args.port), partial(Handler, directory=str(OUTPUT))
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
