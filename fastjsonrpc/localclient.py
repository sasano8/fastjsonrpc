from typing import List, Optional, Set

import requests
from requests import PreparedRequest
from starlette.types import Message


def include_keys(dic: dict, keys: Set[str] = set()):
    copied = {}
    for key in keys:
        if key in dic:
            copied[key] = dic[key]
    return copied


def exclude_keys(dic: dict, keys: Set[str] = set()):
    copied = dic.copy()
    for key in keys:
        dic.pop(key, None)
    return copied


class LocalClient:
    """Call ASGI application without going through ASGI application server."""

    def __init__(self, asgi, scope=None, send=None, receive=None):
        self.app = asgi
        self.scope = self._init_scope(scope)
        self.send = send
        self.receive = receive

    @classmethod
    def from_asgi(cls, asgi):
        return cls(asgi)

    @classmethod
    def from_scope(cls, scope, send, receive):
        return cls(scope["app"], scope, send, receive)

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

    @staticmethod
    def _init_scope(scope: Optional[dict] = None):
        # cookiesはheadersに設定されている
        if scope is not None:
            copied = include_keys(scope, {"headers", "state"})
            return copied
        else:
            return {"headers": [], "state": {}}

    def _create_request(self, method: str, url: str, kwargs):
        if not url.startswith("/"):
            raise ValueError("Must be first /.")

        url = "http://localhost" + url
        req = requests.Request(method, url, **kwargs)
        request = req.prepare()
        return request

    def _create_scope(self, request: PreparedRequest):
        import urllib.parse

        parsed_url = urllib.parse.urlparse(request.path_url)
        scope: dict = {
            "type": "http",
            "headers": [],
            "method": request.method,
            "path": parsed_url.path,
            "query_string": parsed_url.query,
            "scheme": parsed_url.scheme,
        }
        return scope

    async def call_in_context(self, method: str, url: str, **kwargs) -> List[Message]:
        request = self._create_request(method, url, kwargs)
        scope = self._create_scope(request)
        scope.update(self.scope)  # 現在のscopeを継承する
        return []

    async def call(self, method: str, url: str, **kwargs) -> List[Message]:
        request = self._create_request(method, url, kwargs)
        scope = self._create_scope(request)

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
