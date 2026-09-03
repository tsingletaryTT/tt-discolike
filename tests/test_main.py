from fastapi import FastAPI

from disco.main import app


def test_main_exposes_fastapi_app():
    assert isinstance(app, FastAPI)
