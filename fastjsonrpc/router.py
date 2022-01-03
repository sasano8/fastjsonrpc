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


class ProxyResponse(JSONResponse):
    """
    super().get_route_handler()で処理されたレスポンスをJSONRPCの仕様に従い、idを付与して返したい。
    デフォルトハンドラーは、結果をオブジェクトをレスポンスに変換する際にバイト表現にしてしまうため、idを付与できない。
    なので、レスポンス作成時にバイト表現にせずに、idを付与した後にバイト表現にする。
    また、レスポンス生成時にcontent-lengthを計算しヘッダを生成するため、
    属性(body)の上書きで対応するとcontent-lengthの不一致になってしまう（uvicornなどレスポンス検証器を通すとエラーが発生）。
    そのような理由があり、意図が分かりにくいコードになっている。
    """

    def __init__(
        self,
        content=None,
        status_code: int = 200,
        headers: dict = None,
        media_type: str = None,
        background=None,
    ):
        self.kwargs = {
            "content": content,
            "status_code": status_code,
            "headers": headers,
            "media_type": media_type,
            "background": background,
        }
        self._extend = None
        JSONResponse.__init__(self, **self.kwargs)

    def render(self, content) -> bytes:
        return b""

    def init_headers(self, headers):
        return {}

    @property
    def headers(self):
        return ProxyHeader(self)

    def get_response(self, content):
        # super().get_route_handler()
        # ...
        # response.headers.raw.extend(sub_response.headers.raw)
        # if sub_response.status_code:
        #     response.status_code = sub_response.status_code
        # return response
        self.kwargs["content"] = content
        response = JSONResponse(**self.kwargs)
        if self._extend:
            response.headers.raw.extend(self._extend)

        response.status_code = self.status_code

        return response

    def get_content(self):
        return self.kwargs["content"]


class ProxyHeader:
    def __init__(self, proxy_response: ProxyResponse):
        self.proxy_response = proxy_response

    @property
    def raw(self):
        return self

    def extend(self, value):
        self.proxy_response._extend = value


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
            res: ProxyResponse
            if not request.scope.get("jsonrpc", {}):
                res = await original_route_handler(request)
                res = res.get_response(res.get_content())
                return res
            else:
                body: Union[RpcRequest, RpcRequestNotification] = request.scope[
                    "jsonrpc"
                ]["body"]

                request._body = json.dumps(body.params).encode("utf-8")
                request._json = body.params

                try:
                    res = await original_route_handler(request)
                    res = res.get_response(
                        RpcResponse(result=res.get_content(), id=body.get_id()).dict()
                    )
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

    # @staticmethod
    # async def get_response(
    #     request, dependant, body, dependency_overrides_provider, is_coroutine
    # ):
    #     from fastapi.dependencies.utils import solve_dependencies
    #     from fastapi.routing import run_endpoint_function
    #     from fastapi.routing import serialize_response

    #     solved_result = await solve_dependencies(
    #         request=request,
    #         dependant=dependant,
    #         body=body,
    #         dependency_overrides_provider=dependency_overrides_provider,
    #     )
    #     values, errors, background_tasks, sub_response, _ = solved_result
    #     if errors:
    #         raise RequestValidationError(errors, body=body)

    #     raw_response = await run_endpoint_function(
    #         dependant=dependant, values=values, is_coroutine=is_coroutine
    #     )
    #     response_data = await serialize_response(
    #         field=response_field,
    #         response_content=raw_response,
    #         include=response_model_include,
    #         exclude=response_model_exclude,
    #         by_alias=response_model_by_alias,
    #         exclude_unset=response_model_exclude_unset,
    #         exclude_defaults=response_model_exclude_defaults,
    #         exclude_none=response_model_exclude_none,
    #         is_coroutine=is_coroutine,
    #     )
    #     return response_data

    # @staticmethod
    # async def finalize_response(response_data):
    #     response_args: Dict[str, Any] = {"background": background_tasks}
    #     # If status_code was set, use it, otherwise use the default from the
    #     # response class, in the case of redirect it's 307
    #     if status_code is not None:
    #         response_args["status_code"] = status_code
    #     response = actual_response_class(response_data, **response_args)
    #     response.headers.raw.extend(sub_response.headers.raw)
    #     if sub_response.status_code:
    #         response.status_code = sub_response.status_code
    #     return response


class JsonRpcRouter(PostOnlyRouter):
    dispatcher_cls = JsonRpcRoute

    def __init__(self, **kwargs):
        if kwargs.get("prefix", "") != "":
            raise ValueError("must be empty.")

        if kwargs.get("default_response_class", "") != "":
            raise ValueError("must be empty.")

        route_cls = self.dispatcher_cls._create_router()
        APIRouter.__init__(
            self, route_class=route_cls, default_response_class=ProxyResponse, **kwargs
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
