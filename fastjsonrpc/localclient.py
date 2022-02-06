from typing import List, Set

import requests
from requests import PreparedRequest
from starlette.datastructures import Headers
from starlette.types import Message


def include_keys(dic: dict, keys: Set[str] = set()):
    copied = {}
    for key in keys:
        if key in dic:
            copied[key] = dic[key]
    return copied


class StateLocalClient:
    """Call ASGI application without going through ASGI application server."""

    @classmethod
    def from_asgi(cls, asgi):
        scope = {"app": asgi}
        return cls(scope, None, None)

    def __init__(
        self, scope=None, send=None, receive=None, includes={"headers", "state"}
    ):
        self.__pre_init__(scope)
        self.app = scope["app"]
        self.send = send
        self.receive = receive

        self._scope = include_keys(scope, includes)

    def __pre_init__(self, scope):
        scope.setdefault("state", {})

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

    def _create_request(self, method: str, url: str, kwargs):
        if not url.startswith("/"):
            raise ValueError("Must be first /.")

        url = "http://localhost" + url
        req = requests.Request(method, url, **kwargs)
        request = req.prepare()
        return request

    @classmethod
    def _create_scope(cls, request: PreparedRequest):
        import urllib.parse

        parsed_url = urllib.parse.urlparse(request.path_url)
        scope: dict = {
            "type": "http",
            "method": request.method,
            "path": parsed_url.path,
            "query_string": parsed_url.query,
            "scheme": parsed_url.scheme,
            "headers": cls._create_headers(request),
        }
        return scope

    @classmethod
    def _create_headers(cls, request: PreparedRequest):
        try:
            del request.headers["content-length"]
        except:
            ...

        headers = Headers(request.headers)
        return headers._list

    async def call(self, method: str, url: str, **kwargs) -> List[Message]:
        request = self._create_request(method, url, kwargs)
        scope = self._create_scope(request)
        scope.update(self._scope)
        return await self._call(request, scope)

    async def _call(self, request, scope):
        async def execute():
            result = []

            async def recieve():
                return {
                    "type": "http.request",
                    "more_body": False,
                    "body": request.body.encode("utf8") if request.body else b"",
                }

            async def send(msg):
                result.append(msg)

            _ = await self.app(scope, recieve, send)  # can't get result
            return result

        res = await execute()
        return res


class LocalClient(StateLocalClient):
    """Call ASGI application without going through ASGI application server."""

    def __init__(self, scope=None, send=None, receive=None, includes=set()):
        super().__init__(scope, send, receive, includes)

    def __pre_init__(self, scope):
        ...
