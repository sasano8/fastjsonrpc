from typing import Any, List, Optional, Union

from pydantic import BaseModel, Field


class RpcRequestBase(BaseModel):
    ...


class RpcRequest(RpcRequestBase):
    jsonrpc: str = Field("2.0", const=True)
    method: str
    params: Union[list, dict] = {}
    id: int

    def get_id(self):
        return self.id

    class Config:
        schema_extra = {
            "example": {
                "jsonrpc": "2.0",
                "method": "ping",
                "params": {"msg": "hello"},
                "id": 0,
            }
        }


class RpcRequestNotification(RpcRequestBase):
    jsonrpc: str = Field("2.0", const=True)
    method: str
    params: Union[list, dict] = {}

    def get_id(self):
        return None

    class Config:
        schema_extra = {
            "example": {
                "jsonrpc": "2.0",
                "method": "ping",
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
                    "method": "ping",
                    "params": {"msg": "hello 1"},
                    "id": 0,
                },
                {
                    "jsonrpc": "2.0",
                    "method": "ping",
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
