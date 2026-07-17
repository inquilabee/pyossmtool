"""CLI entry for the local report server."""

from __future__ import annotations

import webbrowser
from pathlib import Path

import uvicorn

from shipgate.server.app import create_app


def run_server(*, host: str = "127.0.0.1", port: int = 8765, open_browser: bool = False) -> None:
    primary_root = Path.cwd()
    app = create_app(primary_root)
    url = f"http://{host}:{port}/"
    print(url)
    if open_browser:
        webbrowser.open(url)
    uvicorn.run(app, host=host, port=port)
