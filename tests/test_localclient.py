import pytest

from fastjsonrpc.localclient import LocalClient
from tests import as_async


@pytest.fixture
def client():
    from fastapi import FastAPI

    api = FastAPI()

    @api.get("/hello")
    def hello():
        return "hello"

    client = LocalClient(api)
    return client


@as_async
async def test_localclient(client: LocalClient):
    result = await client.call(method="GET", url="/hello")
    assert len(result) == 2
    assert result[0]["type"] == "http.response.start"
    assert result[1]["type"] == "http.response.body"
    assert result[1]["body"] == b'"hello"'


@as_async
async def test_localclient_validator(client: LocalClient):
    with pytest.raises(ValueError, match="Must be first /."):
        result = await client.call(method="GET", url="hello")
