import json
from typing import TYPE_CHECKING, Callable, Union

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, parse_obj_as

from . import exceptions
from .schemas import (
    RpcRequest,
    RpcRequestBatch,
    RpcRequestNotification,
    RpcResponse,
    RpcResponseError,
)

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


class NoRenderJSONResponse(JSONResponse):
    def render(self, content):
        return content

    def set_body(self, content):
        self.body = super().render(content)


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

        # if not jsonrpc entrypoint
        if not scope["path"] == "/":
            scope["jsonrpc"] = {}
            await self.app(scope, receive, send)
            return

        req = Request(scope, receive, send)

        try:
            body = await req.body()
        except Exception as e:
            response = JSONResponse(exceptions.InternalServerError(), status_code=200)
            await response(scope, receive, send)
            return

        try:
            body = json.loads(body)
        except Exception as e:
            response = JSONResponse(
                exceptions.ParseError(str(e)).to_dict(), status_code=200
            )
            await response(scope, receive, send)
            return

        try:
            body = parse_obj_as(
                Union[RpcRequest, RpcRequestNotification, RpcRequestBatch], body
            )
        except Exception as e:
            response = JSONResponse(
                exceptions.InvalidRequestError(str(e)).to_dict(),
                status_code=200,
            )
            await response(scope, receive, send)
            return

        if isinstance(body, RpcRequestBatch):
            response = JSONResponse(
                exceptions.InternalServerError(
                    "Not implement batch request."
                ).to_dict(),
                status_code=200,
            )
            await response(scope, receive, send)
            return
        else:
            if body.method not in self._methods:
                response = JSONResponse(
                    exceptions.MethodNotFoundError().to_dict(body.get_id()),
                    status_code=200,
                )
                await response(scope, receive, send)
                return

            scope["jsonrpc"] = {"entry_path": scope["path"], "body": body}
            scope["path"] += body.method
            await scope["router"].__call__(scope, receive, send)
            return

    @staticmethod
    def dispatcher(
        body: Union[RpcRequest, RpcRequestBatch, RpcRequestNotification]
    ) -> Union[RpcResponse, RpcResponseError]:
        ...

    def get_route_handler(self) -> Callable:
        original_route_handler = super().get_route_handler()

        async def custom_route_handler(request: Request) -> Response:
            res: NoRenderJSONResponse
            if not request.scope.get("jsonrpc", {}):
                res = await original_route_handler(request)
                res.set_body(res.body)
                return res
            else:
                body: Union[RpcRequest, RpcRequestNotification] = request.scope[
                    "jsonrpc"
                ]["body"]

                request._body = json.dumps(body.params).encode("utf-8")
                request._json = body.params

                try:
                    res = await original_route_handler(request)
                    res.set_body(RpcResponse(result=res.body, id=body.get_id()).dict())
                    return res
                except exceptions.RpcError as e:
                    err = e.to_dict(body.get_id())
                    return JSONResponse(err)
                except RequestValidationError as e:
                    err = exceptions.InvalidParamsError(str(e)).to_dict(body.get_id())
                    return JSONResponse(err)
                except Exception as e:
                    err = exceptions.InternalServerError(str(e)).to_dict(body.get_id())
                    return JSONResponse(err)

        return custom_route_handler


class JsonRpcRouter(PostOnlyRouter):
    dispatcher_cls = JsonRpcRoute

    def __init__(self, **kwargs):
        if kwargs.get("prefix", "") != "":
            raise ValueError("must be empty.")

        if kwargs.get("default_response_class", "") != "":
            raise ValueError("must be empty.")

        route_cls = self.dispatcher_cls._create_router()
        APIRouter.__init__(
            self,
            route_class=route_cls,
            default_response_class=NoRenderJSONResponse,
            **kwargs
        )
        APIRouter.post(
            self,
            "/",
            status_code=200,
            response_model=self.dispatcher_cls.dispatcher.__annotations__["return"],
        )(self.dispatcher_cls.dispatcher)
        self._methods = route_cls._methods

    def include_router(self, router: "JsonRpcRouter", **kwargs):  # type: ignore
        raise NotImplementedError()

    def post(self, path=None, **kwargs):
        if path == "/":
            raise ValueError("Not allow root.")

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
                    self._methods[name] = func_or_basemodel
                    path = "/" + name
                else:
                    raise NotImplementedError()

            register = APIRouter.post(self, path=path, **kwargs)
            register(func)
            # method(func)
            return func_or_basemodel

        return wrapper


if TYPE_CHECKING:

    class JsonRpcRouter(APIRouter):  # type: ignore
        ...


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


def get_snake_case_converter():
    import re

    # return re.sub(r"(?<!^)(?=[A-Z])", "_", val).lower()

    pattern = re.compile(r"(?<!^)(?=[A-Z])")

    def to_snake_case(val: str):
        return pattern.sub("_", val).lower()

    return to_snake_case
