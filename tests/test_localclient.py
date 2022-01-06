from fastjsonrpc.localclient import LocalClient


def test_localclient():
    import asyncio

    from fastapi import FastAPI

    api = FastAPI()
    client = LocalClient(api)

    @api.get("/hello")
    def hello():
        return "hello"

    result = asyncio.run(client.call(method="GET", url="/hello"))
    assert len(result) == 2
    assert result[0]["type"] == "http.response.start"
    assert result[1]["type"] == "http.response.body"
    assert result[1]["body"] == b'"hello"'
