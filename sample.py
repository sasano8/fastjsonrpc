from fastapi import FastAPI, Depends
from pydantic import BaseModel

from fastjsonrpc import JsonRpcRouter, RpcError

rpc = JsonRpcRouter()


def get_suffix():
    return "!!!"


@rpc.post()
class Echo(BaseModel):
    msg: str = "hello"

    def __call__(self, suffix: str = Depends(get_suffix)):
        return self.msg + suffix


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
