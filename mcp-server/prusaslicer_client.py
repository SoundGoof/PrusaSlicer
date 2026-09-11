#!/usr/bin/env python3
"""Client for the PrusaSlicer plugin server (start PrusaSlicer with --plugin-server).

Standard library only. Usage:

    prusaslicer_client.py ping
    prusaslicer_client.py run 'print(#api.project:objects())'
    prusaslicer_client.py run-file script.lua

The server's port and token are read from plugin-server.json in the PrusaSlicer
data directory. Override with --datadir or the PRUSASLICER_DATADIR environment variable.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


def default_datadir() -> Path:
    env = os.environ.get("PRUSASLICER_DATADIR")
    if env:
        return Path(env)
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", "")) / "PrusaSlicer"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "PrusaSlicer"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "PrusaSlicer"


class PluginServerClient:
    def __init__(self, datadir: Path | None = None, timeout: float = 130.0):
        self.datadir = Path(datadir) if datadir else default_datadir()
        self.timeout = timeout
        self._info: dict | None = None

    @property
    def info(self) -> dict:
        if self._info is None:
            path = self.datadir / "plugin-server.json"
            try:
                self._info = json.loads(path.read_text())
            except FileNotFoundError:
                raise RuntimeError(
                    f"{path} not found. Is PrusaSlicer running with --plugin-server "
                    f"and this data directory?"
                ) from None
        return self._info

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict:
        url = f"http://{self.info['host']}:{self.info['port']}{path}"
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {self.info['token']}")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            try:
                return json.loads(e.read())
            except Exception:
                raise RuntimeError(f"HTTP {e.code}: {e.reason}") from None
        except urllib.error.URLError as e:
            self._info = None  # stale file, re-read next time
            raise RuntimeError(f"cannot reach plugin server at {url}: {e.reason}") from None

    def ping(self) -> dict:
        return self._request("GET", "/ping")

    def run(self, code: str) -> dict:
        """Run a Lua chunk. Returns {"ok", "output", "result", "error"}."""
        return self._request("POST", "/lua", {"code": code})


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--datadir", help="PrusaSlicer data directory holding plugin-server.json")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ping")
    p_run = sub.add_parser("run")
    p_run.add_argument("code")
    p_file = sub.add_parser("run-file")
    p_file.add_argument("path")
    args = ap.parse_args(argv)

    client = PluginServerClient(args.datadir)
    if args.cmd == "ping":
        print(json.dumps(client.ping(), indent=2))
        return 0
    code = args.code if args.cmd == "run" else Path(args.path).read_text()
    res = client.run(code)
    if res.get("output"):
        sys.stdout.write(res["output"])
    if res.get("result"):
        print("=>", res["result"])
    if not res.get("ok"):
        print("error:", res.get("error"), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
