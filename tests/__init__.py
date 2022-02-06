from functools import wraps

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from pydantic import BaseModel

from fastjsonrpc import JsonRpcRouter


def as_async(func):
    import asyncio

    @wraps(func)
    def wrapper(*args, **kwargs):
        coro = func(*args, **kwargs)
        return asyncio.run(coro)

    return wrapper


class EverythingEquals:
    def __eq__(self, other):
        return True


class Match:
    def __init__(self, pattern, to_str=False):
        self.pattern = pattern
        self.to_str = to_str

    def __eq__(self, other):
        import re

        if self.to_str:
            other = str(other)

        return re.search(self.pattern, other)


IGNORE = EverythingEquals()


def REQ(method, params={}, id=None):
    return {"jsonrpc": "2.0", "method": method, "params": params, "id": id}


def NOTIFY(method, params={}, id=None):
    return {"jsonrpc": "2.0", "method": method, "params": params}


def OK(id, result):
    return {"jsonrpc": "2.0", "result": result, "id": id}


def ERR(id, code, message, data):
    return {
        "jsonrpc": "2.0",
        "error": {
            "code": code,
            "message": message,
            "data": data,
        },
        "id": id,
    }


def _sample_app_router():
    api = JsonRpcRouter()

    @api.post()
    class Echo(BaseModel):
        msg: str

        def __call__(self):
            return self.msg

    @api.post()
    class Error(BaseModel):
        msg: str

        def __call__(self):
            raise Exception(self.msg)

    @api.post()
    class RpcError(BaseModel):
        msg: str

        def __call__(self):
            from fastjsonrpc.exceptions import RpcError

            raise RpcError(self.msg)

    @api.post()
    class UpdateState(BaseModel):
        def __call__(self, req: Request):
            count = req.state._state.getdefault("countup", 0)
            req.state.countup += count
            return req.state.countup

    app = FastAPI()
    app.include_router(api)
    return app, api


def _sample_app():
    app, api = _sample_app_router()
    return app


@pytest.fixture
def sample_app():
    return _sample_app()


@pytest.fixture
def client():
    app = _sample_app()
    client = TestClient(app)
    return client
