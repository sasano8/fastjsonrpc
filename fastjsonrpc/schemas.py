from typing import Any, List, Optional, Union

from pydantic import BaseModel, Field, validator


class RpcRequestBase(BaseModel):
    ...


class RpcRequest(RpcRequestBase):
    jsonrpc: str = Field("2.0", const=True)
    method: str
    params: Optional[Union[list, dict]] = {}
    id: int

    @validator("method")
    def is_not_empty(cls, v):
        if v == "":
            from .exceptions import MethodNotFoundError

            raise MethodNotFoundError()
        else:
            return v

    def get_id(self):
        return self.id

    class Config:
        schema_extra = {
            "example": {
                "jsonrpc": "2.0",
                "method": "echo",
                "params": {"msg": "hello"},
                "id": 1,
            }
        }


class RpcRequestNotification(RpcRequestBase):
    jsonrpc: str = Field("2.0", const=True)
    method: str
    params: Optional[Union[list, dict]] = {}

    @validator("method")
    def is_not_empty(cls, v):
        if v == "":
            from .exceptions import MethodNotFoundError

            raise MethodNotFoundError()
        else:
            return v

    def get_id(self):
        return None

    class Config:
        schema_extra = {
            "example": {
                "jsonrpc": "2.0",
                "method": "echo",
                "params": {"msg": "hello"},
            }
        }


class RpcRequestBatch(RpcRequestBase):
    __root__: List[Union[RpcRequest, RpcRequestNotification]]

    class Config:
        schema_extra = {
            "example": [
                {
                    "jsonrpc": "2.0",
                    "method": "echo",
                    "params": {"msg": "hello 1"},
                    "id": 0,
                },
                {
                    "jsonrpc": "2.0",
                    "method": "echo",
                    "params": {"msg": "hello 2"},
                },
            ]
        }


class RpcResponse(BaseModel):
    jsonrpc: str = Field("2.0", const=True)
    result: Any
    id: Optional[int] = None


class ErrorInfo(BaseModel):
    code: int
    message: str
    data: Optional[Any] = None


class RpcResponseError(BaseModel):
    jsonrpc: str = Field("2.0", const=True)
    error: ErrorInfo
    id: Optional[int] = None


class RpcEntryPoint(BaseModel):
    __root__: Union[RpcRequest, RpcRequestBatch, RpcRequestNotification]
    _is_jsonrpc_entrypoint: bool = True

    def __call__(self) -> Union[RpcResponse, RpcResponseError]:
        """jsonrpc entry point."""
