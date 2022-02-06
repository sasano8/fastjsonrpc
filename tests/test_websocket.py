import json

from fastapi.testclient import TestClient

from fastjsonrpc.exceptions import (
    InternalServerError,
    InvalidParamsError,
    InvalidRequestError,
    MethodNotFoundError,
    ParseError,
    RpcBaseError,
    RpcError,
)
from fastjsonrpc.websocket import JsonRpcWebSocket
from tests import ERR, IGNORE, OK, REQ, _sample_app, _sample_app_router, as_async


def create_mock(receive_val) -> JsonRpcWebSocket:
    from asyncio import Future

    def future(val):

        f = Future()
        f.set_result(val)
        return f

    assert isinstance(receive_val, (str, bytes))

    app, router = _sample_app_router()
    scope = {"type": "websocket", "app": app, "router": app.router}
    mock = JsonRpcWebSocket(scope, None, None, router)
    mock.receive_text = lambda: future(receive_val)  # type: ignore
    mock.send_text = lambda val: future(None)  # type: ignore
    return mock


@as_async
async def test_create_mock():
    mock = create_mock("aaa")
    assert await mock.receive_text() == "aaa"
    assert await mock.send_text("aaa") is None


@as_async
async def test_receive_rpc_response():
    payload = REQ("echo", {"msg": "hello"}, id=0)
    mock = create_mock(json.dumps(payload))
    res = await mock.receive_rpc_response()
    assert res == OK(id=0, result="hello")

    payload = REQ("rpc_error", {"msg": "err!"}, id=0)
    mock = create_mock(json.dumps(payload))
    res = await mock.receive_rpc_response()
    assert res == ERR(
        id=None,  # TODO: return id
        code=RpcError.code,
        message=RpcError.message,
        data="err!",
    )

    payload = REQ("error", {"msg": "err!"}, id=0)
    mock = create_mock(json.dumps(payload))
    res = await mock.receive_rpc_response()
    assert res == ERR(
        id=None,  # TODO: return id
        code=InternalServerError.code,
        message=InternalServerError.message,
        data=None,
    )


@as_async
async def test_receive_jsonrpc_error():
    mock = create_mock("")
    res = await mock.receive_rpc_response()
    assert res == ERR(
        id=None,
        code=ParseError.code,
        message=ParseError.message,
        data=IGNORE,
    )

    mock = create_mock("a")
    res = await mock.receive_rpc_response()
    assert res == ERR(
        id=None,
        code=ParseError.code,
        message=ParseError.message,
        data=IGNORE,
    )

    mock = create_mock("1")
    res = await mock.receive_rpc_response()
    assert res == ERR(
        id=None,
        code=InvalidRequestError.code,
        message=InvalidRequestError.message,
        data=IGNORE,
    )

    mock = create_mock("null")
    res = await mock.receive_rpc_response()
    assert res == ERR(
        id=None,
        code=InvalidRequestError.code,
        message=InvalidRequestError.message,
        data=IGNORE,
    )

    mock = create_mock("{}")
    res = await mock.receive_rpc_response()
    assert res == ERR(
        id=None,
        code=InvalidRequestError.code,
        message=InvalidRequestError.message,
        data=IGNORE,
    )

    mock = create_mock('{"jsonrpc": "2.0", "method": "xxx", "params": {}}')
    res = await mock.receive_rpc_response()
    assert res == ERR(
        id=None,
        code=MethodNotFoundError.code,
        message=MethodNotFoundError.message,
        data=IGNORE,
    )


def test_request():
    from fastapi import Depends, FastAPI
    from pydantic import BaseModel

    from fastjsonrpc import JsonRpcRouter

    rpc = JsonRpcRouter()

    @rpc.post()
    class Echo(BaseModel):
        msg: str

        def __call__(self):
            return self.msg

    @rpc.websocket("/ws")
    async def websocket_endpoint(
        websocket: JsonRpcWebSocket = Depends(rpc.get_websocket),
    ):
        # TODO: websocketインスタンスがstarlette.websocketになっている
        # TODO: routerがfastapiデフォルトルータになっている
        {
            "type": "websocket",
            "schema": "ws",
            "router": "fastapi.routing.APIRouter",
            "path": "/jsonrpc/ws",
            "root_path": "",
        }

        await websocket.accept()
        await websocket.send_json({"msg": "Hello WebSocket"})
        res = await websocket.receive_rpc_response()
        await websocket.send_json(res)
        await websocket.close()

    app = FastAPI()
    app.include_router(rpc, prefix="/jsonrpc")

    client = TestClient(app)
    with client.websocket_connect("/jsonrpc/ws") as websocket:
        assert websocket.receive_json() == {"msg": "Hello WebSocket"}
        websocket.send_json(REQ("echo", {"msg": "hello"}, id=1))
        data = websocket.receive_json()
        assert data == OK(id=1, result="hello")


def test_websocket_publish():
    from fastapi import FastAPI
    from pydantic import BaseModel

    from fastjsonrpc import JsonRpcRouter

    rpc = JsonRpcRouter()

    @rpc.post()
    class Echo(BaseModel):
        msg: str

        def __call__(self):
            return self.msg

    from starlette.endpoints import WebSocketEndpoint
    from starlette.websockets import WebSocket

    @rpc.websocket_route("/ws")
    class WebSocketTicks(WebSocketEndpoint):
        encoding = "json"

        async def on_connect(self, websocket: WebSocket) -> None:
            import asyncio

            await websocket.accept()
            self.rpc = rpc.get_websocket(websocket)
            self._task = asyncio.create_task(self.tick(websocket))

        async def on_disconnect(self, websocket: WebSocket, close_code: int) -> None:
            import asyncio

            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                ...

        async def on_receive(self, websocket: WebSocket, data) -> None:
            # TODO: テキストにも対応させる（requests互換風）
            res = await self.rpc.post(data)
            await websocket.send_json(res)

        async def tick(self, websocket: WebSocket) -> None:
            import asyncio

            await asyncio.sleep(0.5)
            rpc = self.rpc
            count = 0
            while True:
                count += 1
                res = await rpc.post(
                    {
                        "jsonrpc": "2.0",
                        "method": "echo",
                        "params": {"msg": "hello"},
                        "id": count,
                    }
                )
                await websocket.send_json(res)

    app = FastAPI()
    app.include_router(rpc, prefix="/jsonrpc")

    client = TestClient(app)
    with client.websocket_connect("/jsonrpc/ws") as websocket:
        websocket.send_json(
            {"jsonrpc": "2.0", "method": "echo", "params": {"msg": "send"}, "id": -1}
        )
        data = websocket.receive_json()
        assert data == {"jsonrpc": "2.0", "result": "send", "id": -1}
        data = websocket.receive_json()
        assert data == {"jsonrpc": "2.0", "result": "hello", "id": 1}
        data = websocket.receive_json()
        assert data == {"jsonrpc": "2.0", "result": "hello", "id": 2}


"""
やること
1. websocketの命名規約を/socket_nameとする
    そうすれば/でjsonrpcへのパスを得られる
2. jprcrouterへの参照を持つ
    JprcRouterインスタンスをそのまま参照すればよい？
        rpc.create_websocket(websocket)
3. jprcrouterへのパスへの参照を持つ
    jprcrouter自体はパス情報を持たない
        fastapiが全体的なパスを理解している
4. websocketroute
    fastapiを介せず、websocketrouteを直接追加している
    通常は、get_route_handlerでハンドラを得る
    jprcrouterパスへ参照を取得する手段がない


async def handle(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self.app(scope, receive, send)

def websocket_session(func: typing.Callable) -> ASGIApp:
    # assert asyncio.iscoroutinefunction(func), "WebSocket endpoints must be async"

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        session = WebSocket(scope, receive=receive, send=send)
        await func(session)

    return app

class WebSocketRoute(BaseRoute):
    def __init__(
        self, path: str, endpoint: typing.Callable, *, name: str = None
    ) -> None:
        assert path.startswith("/"), "Routed paths must start with '/'"
        self.path = path
        self.endpoint = endpoint
        self.name = get_name(endpoint) if name is None else name

        if inspect.isfunction(endpoint) or inspect.ismethod(endpoint):
            # Endpoint is function or method. Treat it as `func(websocket)`.
            self.app = websocket_session(endpoint)
        else:
            # Endpoint is a class. Treat it as ASGI.
            self.app = endpoint

        self.path_regex, self.path_format, self.param_convertors = compile_path(path)

    def matches(self, scope: Scope) -> typing.Tuple[Match, Scope]:
        if scope["type"] == "websocket":
            match = self.path_regex.match(scope["path"])
            if match:
                matched_params = match.groupdict()
                for key, value in matched_params.items():
                    matched_params[key] = self.param_convertors[key].convert(value)
                path_params = dict(scope.get("path_params", {}))
                path_params.update(matched_params)
                child_scope = {"endpoint": self.endpoint, "path_params": path_params}
                return Match.FULL, child_scope
        return Match.NONE, {}

    def url_path_for(self, name: str, **path_params: str) -> URLPath:
        seen_params = set(path_params.keys())
        expected_params = set(self.param_convertors.keys())

        if name != self.name or seen_params != expected_params:
            raise NoMatchFound()

        path, remaining_params = replace_params(
            self.path_format, self.param_convertors, path_params
        )
        assert not remaining_params
        return URLPath(path=path, protocol="websocket")

    async def handle(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self.app(scope, receive, send)

    def __eq__(self, other: typing.Any) -> bool:
        return (
            isinstance(other, WebSocketRoute)
            and self.path == other.path
            and self.endpoint == other.endpoint
        )
"""
