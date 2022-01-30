import json
from typing import Union

from starlette.websockets import WebSocket

from fastjsonrpc.schemas import (
    RpcResponse,
    RpcResponseError,
)


config = {
    "jsonrpc_route": "jsonrpc_route",
    "close_on_error": "close_on_error",
    "do_send_ack": "do_send_ack",
}


class JsonRpcWebSocket(WebSocket):
    CLOSE_ON_ERROR: bool = True

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__()
        cls.__config__ = kwargs.get("config", {})

    def _set_entrypoint_path(self, app, entrypoint_path):
        """Called by JsonRPCRouter"""
        from fastjsonrpc.localclient import LocalClient

        self.dispacher = LocalClient(app)
        self.entrypoint = entrypoint_path

    async def post(self, data):
        data = json.dumps(data)
        result = await self.dispacher.call(
            method="POST", url=self.entrypoint, data=data
        )
        body = result[1]["body"]
        return json.loads(body)

    async def request_rpc_text(
        self, rpc_request_text
    ) -> Union[RpcResponse, RpcResponseError]:
        result = await self.dispacher.call(
            method="POST", url=self.entrypoint, data=rpc_request_text
        )
        body = result[1]["body"]
        return body

    async def receive_rpc_response(
        self,
    ) -> Union[RpcResponse, RpcResponseError]:
        data = await self.receive_text()
        res_body = await self.request_rpc_text(data)
        return json.loads(res_body)

    @staticmethod
    def copy_scope(
        scope: dict,
        method: str = "POST",
        excludes={"root_path", "path", "raw_path", "path_params"},
    ):
        tmp = scope.copy()
        tmp["type"] = "http"
        for key in excludes:
            tmp.pop(key, None)
        return tmp
