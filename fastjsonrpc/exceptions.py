from typing import Any, Optional

from .schemas import ErrorInfo, RpcResponseError

""" json rpc specification Error object
-32700: parse error: サーバが無効なJSONを受信しました
-32600: invalid request: 送信されたSONは有効なRequestオブジェクトではありません
-32601: method not found: メソッドが存在しません
-32602: invalid parameter: メソッドのパラメータが無効です
-32603: 内部エラー: 内部JSON-RPCエラー
-32000~-32099: サーバーエラー: 実装定義のサーバエラー用に予約されています
"""


class RpcBaseError(Exception):
    def __init__(self, data: Optional[Any] = None):
        self.data = data

    def to_pydantic(self, id=None):
        error = ErrorInfo(
            code=self.code,  # type: ignore
            message=self.message,  # type: ignore
            data=self.data,
        )
        return RpcResponseError(id=id, error=error)

    def to_dict(self, id=None):
        return self.to_pydantic(id=id).dict()

    def to_json(self, id=None):
        return self.to_pydantic(id=id).json()


class NoInit:
    def __init__(self):
        ...


class ParseError(RpcBaseError):
    code = -32700
    message = "Parse error."
    data = None


class InvalidRequestError(RpcBaseError):
    code = -32600
    message = "Invalid Request."
    data = None


class MethodNotFoundError(NoInit, RpcBaseError):
    code = -32601
    message = "Method not found."
    data = None


class InvalidParamsError(RpcBaseError):
    code = -32602
    message = "Invalid params."
    data = None


class InternalServerError(RpcBaseError):
    code = -32603
    message = "Internal Server Error."
    data = None

    def __init__(self, data: Optional[Any] = None):
        self._data = data


########################
# User Define Exceptions
########################


class RpcError(RpcBaseError):
    code = -32000
    message = "An error occured."
    data = None
