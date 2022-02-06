import json
from typing import Union

from starlette.websockets import WebSocket

from fastjsonrpc.schemas import RpcResponse, RpcResponseError

config = {
    "jsonrpc_route": "jsonrpc_route",
    "close_on_error": "close_on_error",
    "do_send_ack": "do_send_ack",
}


class JsonRpcWebSocket(WebSocket):
    CLOSE_ON_ERROR: bool = True

    @staticmethod
    def get_websocket(self: "JsonRpcRouter", websocket: WebSocket, contexable=False):
        state = websocket.state
        return JsonRpcWebSocket(
            websocket.scope, websocket.receive, websocket.send, self, contexable
        )

    def __init__(self, scope, receive, send, rpc_router, contextable=False) -> None:
        super().__init__(scope, receive, send)

        from fastjsonrpc.localclient import LocalClient

        self.entrypoint = self._analize_entrypoint_path(scope, rpc_router)
        # self.dispacher = LocalClient(scope["app"], scope, contextable=True)
        self.dispacher = LocalClient(scope["app"])

    @classmethod
    def _analize_entrypoint_path(cls, scope, rpc_router):
        entrypoint = cls._filter_entrypoint(rpc_router, scope["router"])[0]
        path = entrypoint.path.split("/")[1:-1]
        entrypoint_path = "/" + "/".join(path)
        if len(entrypoint_path) > 1:
            entrypoint_path = entrypoint_path + "/"

        return entrypoint_path

    @staticmethod
    def _filter_entrypoint(rpc_router, router):
        entrypoint = rpc_router.routes[0]

        def filter_jsonrpc_router(route):
            return entrypoint.__class__ is route.__class__

        return list(filter(filter_jsonrpc_router, router.routes))

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__()
        cls.__config__ = kwargs.get("config", {})

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
