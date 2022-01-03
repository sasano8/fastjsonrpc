# fastapi_jsonrpc
<!--
[![Version](https://img.shields.io/pypi/v/asy)](https://pypi.org/project/asy)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
-->

# Requirement

- Python 3.8+

# Installation

``` shell
pip install xxxxxxxxxxxxxxxxxxxxxxxx
```

# Getting started
``` Python
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastjsonrpc import JsonRpcRouter, RpcError
from pydantic import BaseModel

rpc = JsonRpcRouter()

def get_suffix():
    return "!!!"

@rpc.post()
class Echo(BaseModel):
    msg: str

    def __call__(self, suffix: str = Depends(get_suffix)):
        return self.msg

@rpc.post()
class Error(BaseModel):
    msg: str

    def __call__(self):
        raise YourAppError(self.msg)

class YourAppError(RpcError):
    code = -32001  # -32001, -32002, ...
    message = "Application exception."

app = FastAPI()
app.include_router(rpc)

# test

client = TestClient(app)
res = client.post("/", json={
    "jsonrpc": "2.0",
    "id": 1,
    "method": "echo",
    "params": {"msg": "hello"}
})
assert res.json()["result"] == "hello"

res = client.post("/", json={
    "jsonrpc": "2.0",
    "id": 2,
    "method": "error",
    "params": {"msg": "test error"}
})
assert res.json()["error"]["message"] == "Application exception."
assert res.json()["error"]["data"] == "test error"
```

# Development - Contributing

## setup

``` shell
poetry install
pre-commit install
```

## fomart script & test

``` shell
make
```

## running and debugging server

To debug the json rpc server with vscode.

- Run `Python: debug server` from `running and debugging`.
