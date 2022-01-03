from fastapi import FastAPI
from pydantic import BaseModel

from fastjsonrpc import JsonRpcRouter, RpcError

rpc = JsonRpcRouter()


@rpc.post()
class Echo(BaseModel):
    msg: str = "hello"

    def __call__(self):
        return self.msg


@rpc.post()
class Error(BaseModel):
    msg: str = "error occured."

    def __call__(self):
        raise YourAppError(self.msg)


class YourAppError(RpcError):
    code = -32001  # -32001, -32002, ...
    message = "Application exception."


app = FastAPI()
app.include_router(rpc)
