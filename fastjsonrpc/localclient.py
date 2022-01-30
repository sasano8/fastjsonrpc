from typing import List

import requests
from starlette.types import Message


class LocalClient:
    """Call ASGI application without going through ASGI application server."""

    def __init__(self, asgi):
        self.app = asgi

    # def create_scope(self):

    #     return {
    #         "type": "http",  # required
    #         "asgi": {"version": "3.0", "spec_version": "2.1"},
    #         # "http_version": "1.1",
    #         # "server": ["127.0.0.1", 8000],
    #         # "client": ["127.0.0.1", 46612],
    #         # "scheme": "http",
    #         "method": "GET",
    #         "root_path": "",
    #         "path": "/users",
    #         "raw_path": b"/users",
    #         "query_string": b"name=bob",
    #         "headers": [
    #             # (b"host", b"127.0.0.1:8000"),
    #             (b"user-agent", b"python-requests/2.26.0"),
    #             (b"accept-encoding", b"gzip, deflate"),
    #             (b"accept", b"*/*"),
    #             (b"connection", b"keep-alive"),
    #         ],
    #     }

    async def call(self, method: str, url: str, **kwargs) -> List[Message]:
        if not url.startswith("/"):
            raise ValueError("Must be first /.")

        url = "http://localhost" + url
        req = requests.Request(method, url, **kwargs)
        p = req.prepare()

        import urllib.parse

        parsed_url = urllib.parse.urlparse(p.path_url)

        # p.url = http://testclient/?name=bob
        # p.path_url = /?name=bob

        scope: dict = {
            "type": "http",
            "local": True,
            "headers": {},
            "method": p.method,
            "path": parsed_url.path,
            "query_string": parsed_url.query,
            "scheme": parsed_url.scheme,
        }

        async def execute():
            result = []

            async def recieve():
                return {
                    "type": "http.request",
                    "more_body": False,
                    "body": p.body.encode("utf8") if p.body else b"",
                }

            async def send(msg):
                result.append(msg)

            _ = await self.app(scope, recieve, send)  # can't get result
            return result

        res = await execute()
        return res
