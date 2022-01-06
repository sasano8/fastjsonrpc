import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from fastjsonrpc import JsonRpcRouter


#################################
# router test
#################################
def test_dont_use_prefix():
    api = JsonRpcRouter()

    # must be no nest
    with pytest.raises(ValueError, match="must be empty"):
        JsonRpcRouter(prefix="/xxxx")

    with pytest.raises(NotImplementedError):
        api.include_router(JsonRpcRouter(), prefix="/xxx")


def test_not_allow_func():
    def hello():
        ...

    api = JsonRpcRouter()
    with pytest.raises(NotImplementedError):
        assert api.post()(hello)


def test_must_be_callable():

    api = JsonRpcRouter()

    with pytest.raises(TypeError, match="Must be Callable"):

        @api.post("/not_callable")
        class NotCallable(BaseModel):
            msg: str


def test_post_only():
    api = JsonRpcRouter()

    class Hello(BaseModel):
        msg: str = "hello"

        def __call__(self):
            return self.msg

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


#################################
# client test
#################################
@pytest.fixture
def client():
    api = JsonRpcRouter()

    @api.post()
    class Echo(BaseModel):
        msg: str

        def __call__(self):
            return self.msg

    @api.post()
    class Error(BaseModel):
        msg: str

        def __call__(self):
            raise Exception(self.msg)

    @api.post()
    class RpcError(BaseModel):
        msg: str

        def __call__(self):
            from fastjsonrpc.exceptions import RpcError

            raise RpcError(self.msg)

    app = FastAPI()
    app.include_router(api)
    client = TestClient(app)
    return client


def test_parse_error(client: TestClient):
    from fastjsonrpc.exceptions import ParseError

    assert ParseError.code == -32700

    response = client.post("/", data="")
    assert response.status_code == 200
    assert response.json() == {
        "jsonrpc": "2.0",
        "error": {
            "code": ParseError.code,
            "message": "Parse error.",
            "data": "Expecting value: line 1 column 1 (char 0)",
        },
        "id": None,
    }


def test_invalid_error(client: TestClient):
    from fastjsonrpc.exceptions import InvalidRequestError

    assert InvalidRequestError.code == -32600

    response = client.post("/", json={})
    assert response.status_code == 200
    result = response.json()
    assert result["error"].pop("data")
    assert result == {
        "jsonrpc": "2.0",
        "error": {
            "code": InvalidRequestError.code,
            "message": "Invalid Request.",
            # "data": "...",
        },
        "id": None,
    }


def test_method_not_found_error(client: TestClient):
    from fastjsonrpc.exceptions import MethodNotFoundError
    from fastjsonrpc.schemas import RpcRequestNotification as Req

    assert MethodNotFoundError.code == -32601

    response = client.post("/", json=Req(method="xxx").dict())
    assert response.status_code == 200
    assert response.json() == {
        "jsonrpc": "2.0",
        "error": {
            "code": MethodNotFoundError.code,
            "message": "Method not found.",
            "data": None,
        },
        "id": None,
    }

    response = client.post("/", json=Req(method="").dict())
    assert response.status_code == 200
    assert response.json()["error"]["code"] == MethodNotFoundError.code

    response = client.post("/", json=Req(method="/").dict())
    assert response.status_code == 200
    assert response.json()["error"]["code"] == MethodNotFoundError.code


def test_invalid_params_error(client: TestClient):
    from fastjsonrpc.exceptions import InvalidParamsError
    from fastjsonrpc.schemas import RpcRequestNotification as Req

    assert InvalidParamsError.code == -32602

    response = client.post("/", json=Req(method="echo", params={}).dict())
    assert response.status_code == 200
    result = response.json()
    assert result["error"].pop("data")
    assert result == {
        "jsonrpc": "2.0",
        "error": {
            "code": InvalidParamsError.code,
            "message": "Invalid params.",
            # "data": "...",
        },
        "id": None,
    }


def test_internal_server_error(client: TestClient):
    from fastjsonrpc.exceptions import InternalServerError
    from fastjsonrpc.schemas import RpcRequestNotification as Req

    assert InternalServerError.code == -32603

    response = client.post("/", json=Req(method="error", params={"msg": "_"}).dict())
    assert response.status_code == 200
    assert response.json() == {
        "jsonrpc": "2.0",
        "error": {
            "code": InternalServerError.code,
            "message": "Internal Server Error.",
            "data": None,
        },
        "id": None,
    }


def test_rpc_error(client: TestClient):
    from fastjsonrpc.exceptions import RpcError
    from fastjsonrpc.schemas import RpcRequestNotification as Req

    assert RpcError.code == -32000

    response = client.post(
        "/", json=Req(method="rpc_error", params={"msg": "_"}).dict()
    )
    assert response.status_code == 200
    assert response.json() == {
        "jsonrpc": "2.0",
        "error": {
            "code": RpcError.code,
            "message": "An error occured.",
            "data": "_",
        },
        "id": None,
    }


def test_rpc_request_success(client):
    from fastjsonrpc.schemas import RpcRequest

    response = client.post(
        "/", json=RpcRequest(method="echo", params={"msg": "hello!!!"}, id=1).dict()
    )
    assert response.status_code == 200
    assert response.json() == {
        "result": "hello!!!",
        "id": 1,
        "jsonrpc": "2.0",
    }


def test_http_request_success(client):
    response = client.post(
        "/echo",
        json={"msg": "hello!!!"},
    )
    assert response.status_code == 200
    assert response.json() == "hello!!!"


########################################
# complex test
########################################
def test_include_router_prefix():
    from fastjsonrpc.schemas import RpcRequest as Req

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
        json=Req(method="hello1", id=1).dict(),
    )
    assert response.status_code == 200
    assert response.json()["result"] == "hello 1"

    response = client.post(
        "/rpc_2/",
        json=Req(method="hello2", id=1).dict(),
    )
    assert response.status_code == 200
    assert response.json()["result"] == "hello 2"


def test_specifiy_path():
    # TODO: @rpc.post("/echo")
    assert True
