from typing import Iterable

import pytest

from fastjsonrpc.localclient import LocalClient, StateLocalClient
from tests import as_async


@pytest.fixture
def clients():
    from fastapi import FastAPI

    api = FastAPI()

    @api.get("/hello")
    def hello():
        return "hello"

    client1 = LocalClient.from_asgi(api)
    client2 = StateLocalClient.from_asgi(api)
    return client1, client2


@as_async
async def test_localclient(clients: Iterable[LocalClient]):
    for client in clients:
        result = await client.call(method="GET", url="/hello")
        assert len(result) == 2
        assert result[0]["type"] == "http.response.start"
        assert result[1]["type"] == "http.response.body"
        assert result[1]["body"] == b'"hello"'


@as_async
async def test_localclient_validator(clients: Iterable[LocalClient]):
    for client in clients:
        with pytest.raises(ValueError, match="Must be first /."):
            result = await client.call(method="GET", url="hello")
