import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from fastjsonrpc import JsonRpcRouter
from fastjsonrpc.exceptions import (
    InternalServerError,
    InvalidParamsError,
    InvalidRequestError,
    MethodNotFoundError,
    ParseError,
    RpcError,
)
from tests import ERR, IGNORE, NOTIFY, OK, REQ, Match, client, sample_app


#################################
# router test
#################################
def test_not_allow_prefix():
    api = JsonRpcRouter()

    with pytest.raises(ValueError, match="must be empty"):
        JsonRpcRouter(prefix="/xxxx")


def test_not_allow_include_router():
    api = JsonRpcRouter()

    with pytest.raises(NotImplementedError):
        api.include_router(JsonRpcRouter())

    with pytest.raises(NotImplementedError):
        api.include_router(JsonRpcRouter(), prefix="/xxx")


def test_not_allow_default_response_class():
    from fastapi.responses import JSONResponse

    assert JsonRpcRouter(default_response_class=None)
    with pytest.raises(ValueError, match="'default_response_class' is not allowed"):
        JsonRpcRouter(default_response_class=JSONResponse)


def test_not_allow_route_class():
    from fastapi.routing import APIRoute

    assert JsonRpcRouter(route_class=None)
    with pytest.raises(ValueError, match="'route_class' is not allowed"):
        JsonRpcRouter(route_class=APIRoute)


def test_not_allow_func():
    def hello():
        ...  # pragma: no cover

    hello()

    api = JsonRpcRouter()
    with pytest.raises(NotImplementedError):
        assert api.post()(hello)


def test_must_be_callable():

    api = JsonRpcRouter()

    with pytest.raises(TypeError, match="Must be Callable"):

        @api.post("/not_callable")
        class NotCallable(BaseModel):
            msg: str


def test_not_allow_root():

    api = JsonRpcRouter()

    with pytest.raises(ValueError, match="Not allow root."):
        api.post("/")


def test_post_only():
    api = JsonRpcRouter()

    class Hello(BaseModel):
        msg: str = "hello"

        def __call__(self):
            ...  # pragma: no cover

    # must be post only
    assert api.post()(Hello)
    with pytest.raises(NotImplementedError):
        assert api.get()(Hello)
    with pytest.raises(NotImplementedError):
        assert api.put()(Hello)
    with pytest.raises(NotImplementedError):
        assert api.delete()(Hello)
    with pytest.raises(NotImplementedError):
        assert api.options()(Hello)
    with pytest.raises(NotImplementedError):
        assert api.head()(Hello)
    with pytest.raises(NotImplementedError):
        assert api.patch()(Hello)
    with pytest.raises(NotImplementedError):
        assert api.trace()(Hello)


def test_error_code():
    assert ParseError.code == -32700
    assert InvalidRequestError.code == -32600
    assert MethodNotFoundError.code == -32601
    assert InvalidParamsError.code == -32602
    assert InternalServerError.code == -32603
    assert RpcError.code == -32000


def test_parse_error(client: TestClient):
    response = client.post("/", data="")
    assert response.status_code == 200
    assert response.json() == ERR(
        id=None,
        code=ParseError.code,
        message="Parse error.",
        data="Expecting value: line 1 column 1 (char 0)",
    )

    response = client.post("/", data="a")
    assert response.status_code == 200
    assert response.json() == ERR(
        id=None,
        code=ParseError.code,
        message="Parse error.",
        data="Expecting value: line 1 column 1 (char 0)",
    )


@pytest.mark.parametrize(
    "req, res",
    [
        (
            {},
            ERR(
                id=None,
                code=InvalidRequestError.code,
                message="Invalid Request.",
                data=IGNORE,
            ),
        ),
        (
            NOTIFY("xxx"),
            ERR(
                id=None,
                code=MethodNotFoundError.code,
                message="Method not found.",
                data=None,
            ),
        ),
        (
            NOTIFY(""),
            ERR(
                id=None,
                code=MethodNotFoundError.code,
                message=MethodNotFoundError.message,
                data=None,
            ),
        ),
        (
            NOTIFY("/"),
            ERR(
                id=None,
                code=MethodNotFoundError.code,
                message=MethodNotFoundError.message,
                data=None,
            ),
        ),
        # FIXME: METHOD NOT FOUNDが返るはずが返らない
        # assert response.status_code == 200
        # assert response.json() == ERR(
        #     id=None, code=MethodNotFoundError.code, message="Method not found.", data=IGNORE
        # )
        (
            NOTIFY("echo"),
            ERR(
                id=None,
                code=InvalidParamsError.code,
                message=InvalidParamsError.message,
                data=Match("msg.*field.*required", to_str=True),
            ),
        ),
    ],
)
def test_invalid_request(client: TestClient, req, res):

    response = client.post("/", json=req)
    assert response.status_code == 200
    assert response.json() == res


@pytest.mark.parametrize(
    "req, res, exc",
    [
        (REQ("echo", {"msg": "hello!!!"}, id=1), OK(id=1, result="hello!!!"), None),
        (
            NOTIFY("error", {"msg": "_"}),
            ERR(
                id=None,
                code=InternalServerError.code,
                message=InternalServerError.message,
                data=None,
            ),
            Exception("_"),
        ),
        (
            NOTIFY("rpc_error", {"msg": "_"}),
            ERR(
                id=None,
                code=RpcError.code,
                message=RpcError.message,
                data="_",
            ),
            RpcError("_"),
        ),
    ],
)
def test_valid_request(sample_app, req, res, exc):
    client = TestClient(sample_app, raise_server_exceptions=True)
    client2 = TestClient(sample_app, raise_server_exceptions=False)

    # jsonrpc request
    response = client2.post("/", json=req)
    assert response.status_code == 200
    assert response.json() == res

    # direct request
    if "result" in res:
        response = client2.post("/" + req["method"], json=req["params"])
        assert response.status_code == 200
        assert response.json() == res["result"]

        response = client.post("/" + req["method"], json=req["params"])
        assert response.status_code == 200
        assert response.json() == res["result"]

    elif "error" in res:
        method = "/" + req["method"]
        params = req["params"]

        response = client2.post(method, json=params)
        assert response.status_code == 500  # TODO: 500以外も返せるようにする

        with pytest.raises(exc.__class__, match=str(exc)):
            response = client.post(method, json=params)

    else:
        raise Exception()  # pragma: no cover


########################################
# complex test
########################################
def test_include_router_prefix():
    rpc_1 = JsonRpcRouter()
    rpc_2 = JsonRpcRouter()

    @rpc_1.post()
    class Hello1(BaseModel):
        def __call__(self):
            return "hello 1"

    @rpc_2.post()
    class Hello2(BaseModel):
        def __call__(self):
            return "hello 2"

    app = FastAPI()
    app.include_router(rpc_1, prefix="/rpc_1")
    app.include_router(rpc_2, prefix="/rpc_2")
    client = TestClient(app)

    response = client.post(
        "/rpc_1/",
        json=REQ("hello1", {}, id=1),
    )
    assert response.status_code == 200
    assert response.json() == OK(id=1, result="hello 1")

    response = client.post(
        "/rpc_2/",
        json=REQ("hello2", {}, id=1),
    )
    assert response.status_code == 200
    assert response.json() == OK(id=1, result="hello 2")


def test_specifiy_path():
    # TODO: @rpc.post("/echo")
    assert True


def test_headers():
    # TODO: test headers
    ...


def test_cookies():
    ...
