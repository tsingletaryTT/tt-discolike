from __future__ import annotations

import os

import uvicorn

from disco.app import create_app

app = create_app()


def run() -> None:
    host = os.environ.get("DISCO_HOST", "127.0.0.1")
    port = int(os.environ.get("DISCO_CATALOG_PORT", "8760"))
    uvicorn.run("disco.main:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    run()
