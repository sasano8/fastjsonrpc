import asyncio
import json
import logging
from asyncio.log import logger
from sys import prefix
from typing import TYPE_CHECKING, Any, Callable, Coroutine, Optional, Union
from urllib import response

from fastapi import APIRouter, HTTPException, Request, Response, background
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, parse_obj_as
from pydantic.error_wrappers import ErrorWrapper
from starlette.websockets import WebSocket

from . import exceptions
from .handler import (
    DispatchRequest,
    JsonRpcFutre,
    JsonRpcRequest,
    LocalResponse,
    get_request_handler,
)
from .schemas import (
    RpcEntryPoint,
    RpcRequest,
    RpcRequestBatch,
    RpcRequestNotification,
    RpcResponse,
    RpcResponseError,
)
from .websocket import JsonRpcWebSocket

logger = logging.getLogger(__name__)
logger.setLevel("DEBUG")


# https://fastapi.tiangolo.com/advanced/custom-request-and-route/


MSG_POST_ONLY = "Only POST methods are allowed in JSON RPC."


class PostOnlyRouter(APIRouter):
    def get(self, *args, **kwargs):
        raise NotImplementedError(MSG_POST_ONLY)

    def put(self, *args, **kwargs):
        raise NotImplementedError(MSG_POST_ONLY)

    def delete(self, *args, **kwargs):
        raise NotImplementedError(MSG_POST_ONLY)

    def options(self, *args, **kwargs):
        raise NotImplementedError(MSG_POST_ONLY)

    def head(self, *args, **kwargs):
        raise NotImplementedError(MSG_POST_ONLY)

    def patch(self, *args, **kwargs):
        raise NotImplementedError(MSG_POST_ONLY)

    def trace(self, *args, **kwargs):
        raise NotImplementedError(MSG_POST_ONLY)


from fastapi.responses import PlainTextResponse
from starlette.responses import JSONResponse


class LazyJSONResponse(JSONResponse):
    def __init__(
        self,
        content: Any = None,
        status_code: int = 200,
        headers: dict = None,
        media_type: str = None,
        background=None,
    ) -> None:
        super().__init__(
            content=content,
            status_code=status_code,
            headers=headers,
            media_type=media_type,
            background=background,
        )
        self.content = content


class JsonRpcRoute(APIRoute):
    _methods = {}

    @classmethod
    def _create_router(cls):
        class JsonRpcRoute(cls):
            _methods = {}

        JsonRpcRoute.__name__ = cls.__name__
        return JsonRpcRoute

    async def handle(self, scope, receive, send) -> None:
        if self.methods and scope["method"] not in self.methods:
            if "app" in scope:
                raise HTTPException(status_code=405)
            else:
                response = PlainTextResponse("Method Not Allowed", status_code=405)
            await response(scope, receive, send)
            return

        # If verified
        if "jsonrpc" in scope:
            await self.app(scope, receive, send)
            return

        dispacher = DispatchRequest(scope, receive, send)

        # if direct rpc request
        if not hasattr(self.endpoint, "_is_jsonrpc_entrypoint"):
            await self.app(scope, receive, send)
            return

        rpc = None
        err = None

        try:
            rpc = JsonRpcRequest(scope, receive, send)
            await rpc.validate(self._methods)

            if rpc.is_batch:
                raise NotImplementedError()

            # pathを書き換えて再度ルーティングをし直す
            dispacher.rerouting(
                entrypath=scope["path"], path=scope["path"] + rpc.method
            )
            future = JsonRpcFutre(rpc)
            await scope["router"].__call__(scope, receive, future)
            await future.send_rpc_response(scope, receive, send)
            return

        except RequestValidationError as e:
            err = exceptions.InvalidParamsError(e.errors())

        except exceptions.RpcBaseError as e:
            err = e

        except Exception as e:
            import sys
            import traceback

            # starletteなど関数を実行した場所からの例外と認識してしまうため
            # 本当の例外発生元を取得
            original_tb = e.__traceback__.tb_next.tb_next.tb_next.tb_next
            logger.critical(f"{type(e)} {str(e)}: {str(original_tb.tb_frame)}")
            err = exceptions.InternalServerError(str(e))

        if err:
            response = JSONResponse(err.to_dict(), status_code=200)
            await response(scope, receive, send)
            return

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        jsonalize, invork, create_http_response = get_request_handler(
            dependant=self.dependant,
            body_field=self.body_field,
            status_code=self.status_code,
            response_class=self.response_class,
            response_field=self.secure_cloned_response_field,
            response_model_include=self.response_model_include,
            response_model_exclude=self.response_model_exclude,
            response_model_by_alias=self.response_model_by_alias,
            response_model_exclude_unset=self.response_model_exclude_unset,
            response_model_exclude_defaults=self.response_model_exclude_defaults,
            response_model_exclude_none=self.response_model_exclude_none,
            dependency_overrides_provider=self.dependency_overrides_provider,
        )
        # return app
        async def custom_route_handler(request: Request) -> Response:
            """
            is_direct=True : not via jsonrpc
            is_direct=False: via jsonrpc
            """

            request = JsonRpcRequest(request)
            dispacher = DispatchRequest(request)

            raw_response, background_tasks, sub_response = await invork(request)

            if dispacher.is_direct:
                jsonalized = await jsonalize(raw_response)
                response = create_http_response(
                    jsonalized, background_tasks, sub_response
                )
            else:
                response = LocalResponse(
                    raw_response,
                    background_tasks,
                    sub_response,
                    jsonalize,
                    create_http_response,
                )

            return response

        return custom_route_handler


class JsonRpcRouter(PostOnlyRouter):
    EntryPoint = RpcEntryPoint
    dispatcher_cls = JsonRpcRoute
    RESPONSE_CLASS = LazyJSONResponse
    # RESPONSE_CLASS = ProxyResponse

    if not TYPE_CHECKING:

        def __init__(
            self, prefix="", default_response_class=None, route_class=None, **kwargs
        ):
            # if kwargs.get("prefix", "") != "":
            #     raise ValueError("must be empty.")
            if prefix != "":
                raise ValueError("'prefix' must be empty.")

            if default_response_class is not None:
                raise ValueError(
                    "'default_response_class' is not allowed with jsonrpc router."
                )

            if route_class is not None:
                raise ValueError("'route_class' is not allowed with jsonrpc router.")

            route_cls = self.dispatcher_cls._create_router()
            APIRouter.__init__(
                self,
                route_class=route_cls,
                default_response_class=self.RESPONSE_CLASS,
                **kwargs,
            )

            APIRouter.post(
                self,
                "/",
                status_code=200,
                response_model=self.EntryPoint.__call__.__annotations__["return"],
            )(self.EntryPoint)
            self._methods = route_cls._methods

    def include_router(self, router: "JsonRpcRouter", **kwargs):  # type: ignore
        raise NotImplementedError()

    if not TYPE_CHECKING:

        def post(self, path=None, **kwargs):
            if path == "/":
                raise ValueError("Not allow root.")

            return self._post(path=path, **kwargs)

    def _post(self, path=None, **kwargs):
        to_snake_case = get_snake_case_converter()

        def wrapper(func_or_basemodel):
            nonlocal path
            func = try_get_as_func(func_or_basemodel)
            if func is None:
                raise NotImplementedError()
                func = func_or_basemodel
                if path is None:
                    path = "/" + func.__name__
            else:
                if path is None:
                    name = to_snake_case(func.__name__)
                    path = "/" + name
                else:
                    name = path[1:]

                self._methods[name] = func_or_basemodel

            register = APIRouter.post(self, path=path, **kwargs)
            register(func)
            return func_or_basemodel

        return wrapper

    get_websocket = JsonRpcWebSocket.get_websocket

    # def get_websocket(self, websocket: WebSocket, contexable=False) -> JsonRpcWebSocket:
    #     state = websocket.state
    #     return JsonRpcWebSocket(
    #         websocket.scope, websocket.receive, websocket.send, self, contexable
    #     )


def get_snake_case_converter():
    import re

    # return re.sub(r"(?<!^)(?=[A-Z])", "_", val).lower()

    pattern = re.compile(r"(?<!^)(?=[A-Z])")

    def to_snake_case(val: str):
        return pattern.sub("_", val).lower()

    return to_snake_case


def try_get_as_func(cls):
    import asyncio
    import inspect
    from functools import wraps
    from typing import Callable

    if not inspect.isfunction(cls) and issubclass(cls, BaseModel):
        if not issubclass(cls, Callable):  # type: ignore
            raise TypeError("Must be Callable.")

        if asyncio.iscoroutinefunction(cls.__call__):

            @wraps(cls.__call__)
            async def wrapper(self, *args, **kwargs):
                return await self(*args, **kwargs)

        else:

            @wraps(cls.__call__)
            def wrapper(self, *args, **kwargs):
                return self(*args, **kwargs)

        wrapper.__name__ = cls.__name__
        wrapper.__annotations__["self"] = cls
        return wrapper

    else:
        return None
