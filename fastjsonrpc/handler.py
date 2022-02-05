import asyncio
import json
from typing import Any, Dict, Optional, Type, Union

from fastapi import params
from fastapi.datastructures import Default, DefaultPlaceholder
from fastapi.dependencies.models import Dependant
from fastapi.dependencies.utils import solve_dependencies
from fastapi.encoders import DictIntStrAny, SetIntStr
from fastapi.exceptions import RequestValidationError
from fastapi.routing import run_endpoint_function, serialize_response
from pydantic import ValidationError, parse_obj_as
from pydantic.error_wrappers import ErrorWrapper
from pydantic.fields import ModelField
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from . import exceptions
from .schemas import RpcRequest, RpcRequestBatch, RpcRequestNotification, RpcResponse


def get_request_handler(
    dependant: Dependant,
    body_field: Optional[ModelField] = None,
    status_code: Optional[int] = None,
    response_class: Union[Type[Response], DefaultPlaceholder] = Default(JSONResponse),
    response_field: Optional[ModelField] = None,
    response_model_include: Optional[Union[SetIntStr, DictIntStrAny]] = None,
    response_model_exclude: Optional[Union[SetIntStr, DictIntStrAny]] = None,
    response_model_by_alias: bool = True,
    response_model_exclude_unset: bool = False,
    response_model_exclude_defaults: bool = False,
    response_model_exclude_none: bool = False,
    dependency_overrides_provider: Optional[Any] = None,
):
    # ) -> Callable[[Request], Coroutine[Any, Any, Response]]:
    assert dependant.call is not None, "dependant.call must be a function"
    is_coroutine = asyncio.iscoroutinefunction(dependant.call)
    is_body_form = body_field and isinstance(body_field.field_info, params.Form)
    if isinstance(response_class, DefaultPlaceholder):
        actual_response_class: Type[Response] = response_class.value
    else:
        actual_response_class = response_class

    async def get_body(request: Request):
        # body: Any = None
        # if body_field:
        #     if is_body_form:
        #         body = await request.form()
        #     else:
        #         body_bytes = await request.body()
        #         if body_bytes:
        #             json_body: Any = Undefined
        #             content_type_value = request.headers.get("content-type")
        #             if not content_type_value:
        #                 json_body = await request.json()
        #             else:
        #                 message = email.message.Message()
        #                 message["content-type"] = content_type_value
        #                 if message.get_content_maintype() == "application":
        #                     subtype = message.get_content_subtype()
        #                     if subtype == "json" or subtype.endswith("+json"):
        #                         json_body = await request.json()
        #             if json_body != Undefined:
        #                 body = json_body
        #             else:
        #                 body = body_bytes
        # return body
        return await request.json()

    async def parse_body(request: Request):
        try:
            body = await get_body(request)
        except json.JSONDecodeError as e:
            raise RequestValidationError([ErrorWrapper(e, ("body", e.pos))], body=e.doc)
        except Exception as e:
            raise HTTPException(
                status_code=400, detail="There was an error parsing the body"
            ) from e

        return body

    async def run_endpoint(request: Request, body: Union[bytes, Any]):
        solved_result = await solve_dependencies(
            request=request,
            dependant=dependant,
            body=body,
            dependency_overrides_provider=dependency_overrides_provider,
        )
        values, errors, background_tasks, sub_response, _ = solved_result
        if errors:
            raise RequestValidationError(errors, body=body)

        raw_response = await run_endpoint_function(
            dependant=dependant, values=values, is_coroutine=is_coroutine
        )
        return raw_response, background_tasks, sub_response

    async def jsonalize(raw_response):
        response_data = await serialize_response(
            field=response_field,
            response_content=raw_response,
            include=response_model_include,
            exclude=response_model_exclude,
            by_alias=response_model_by_alias,
            exclude_unset=response_model_exclude_unset,
            exclude_defaults=response_model_exclude_defaults,
            exclude_none=response_model_exclude_none,
            is_coroutine=is_coroutine,
        )
        return response_data

    def create_http_response(response_data, background_tasks, sub_response):
        response_args: Dict[str, Any] = {"background": background_tasks}
        # If status_code was set, use it, otherwise use the default from the
        # response class, in the case of redirect it's 307
        if status_code is not None:
            response_args["status_code"] = status_code
        response = actual_response_class(response_data, **response_args)
        response.headers.raw.extend(sub_response.headers.raw)
        if sub_response.status_code:
            response.status_code = sub_response.status_code
        return response

    async def invork(request: Request):
        body = await parse_body(request)
        raw_response, background_tasks, sub_response = await run_endpoint(request, body)

        if isinstance(raw_response, Response):
            raise NotImplementedError()

        return raw_response, background_tasks, sub_response

    return (
        jsonalize,
        invork,
        create_http_response,
    )


def parse_request(body, typ):
    try:
        validated = parse_obj_as(typ, body)
        return validated, None
    except BaseException as e:
        return None, e


def to_rpc_error(exc):
    if isinstance(exc, ValidationError):
        return exceptions.InvalidRequestError(exc.errors())
    elif isinstance(exc, exceptions.RpcBaseError):
        return exc
    elif isinstance(exc, BaseException):
        return exceptions.InvalidRequestError(str(exc))
    else:
        raise NotImplementedError()


class CopyRequest(Request):
    def __init__(self, *args):
        if len(args) == 1:
            request = args[0]
            scope = request.scope
            receive = request._receive
            send = request._send
        else:
            scope, receive, send = args

        super().__init__(scope, receive, send)


class DispatchRequest(CopyRequest):
    @property
    def _info(self):
        return self.scope.setdefault("_dispatcher", {})

    @property
    def is_direct(self):
        return not self._info.setdefault("rerouting", False)

    def rerouting(self, entrypath, path):
        info: dict = self._info
        if not self.is_direct:
            raise RuntimeError("Already rerouting.")

        info.update(rerouting=True, entrypath=entrypath)
        self.scope["path"] = path


class JsonRpcRequest(CopyRequest):
    def __init__(self, *args):
        super().__init__(*args)
        self._restore_cache()

    @property
    def is_batch(self):
        return isinstance(self._json_request, RpcRequestBatch)

    def __iter__(self):
        if self.is_batch:
            yield from self._json_request.__root__
        else:
            raise TypeError()

    @property
    def jsonrpc(self):
        return self._json_request.jsonrpc

    @property
    def method(self):
        return self._json_request.method

    @property
    def params(self):
        return self._json_request.params

    @property
    def id(self):
        return getattr(self._json_request, "id", None)

    @property
    def _json_request(self):
        return self.scope["_jsonrpc_cache"]["request"]

    async def validate(self, methods={}):
        if hasattr(self.scope, "_jsonrpc_cache"):
            return

        try:
            await self.body()
        except Exception as e:
            raise exceptions.InternalServerError() from e

        try:
            body = await self.json()
        except Exception as e:
            raise exceptions.ParseError(str(e)) from e

        if not isinstance(body, (dict, list)):
            raise exceptions.InvalidRequestError()

        from .schemas import RpcRequest, RpcRequestBatch, RpcRequestNotification

        if isinstance(body, list):
            validated, err = parse_request(body, RpcRequestBatch)
        elif isinstance(body, dict):
            if "id" in body:
                validated, err = parse_request(body, RpcRequest)
            else:
                validated, err = parse_request(body, RpcRequestNotification)
        else:
            validated, err = None, exceptions.InvalidRequestError()

        if err:
            err = to_rpc_error(err)
            raise err

        if not isinstance(validated, RpcRequestBatch):
            if not validated.method in methods:
                raise exceptions.MethodNotFoundError()

        _jsonrpc_cache = {
            "request": validated,
            "_body": b"",
        }

        if isinstance(validated, RpcRequestBatch):
            ...

        else:
            if not validated.method in methods:
                raise exceptions.MethodNotFoundError()

            if isinstance(validated.params, dict):
                _jsonrpc_cache["_json"] = validated.params
            elif isinstance(validated.params, list):
                raise exceptions.InvalidRequestError(
                    f"params must be dict. But given {type(validated.params)}."
                )
            else:
                raise exceptions.InvalidRequestError(
                    f"params must be dict. But given {type(validated.params)}."
                )

        self.scope["_jsonrpc_cache"] = _jsonrpc_cache

    def _restore_cache(self):
        cache = self.scope.get("_jsonrpc_cache", None)
        if cache:
            self._body = cache["_body"]
            self._json = cache["_json"]
            # self._form = cache["_form"]


class LocalResponse:
    def __init__(
        self,
        content: Any = None,
        background=None,
        sub_response=None,
        jsonalize=None,
        create_http_response=None,
    ) -> None:
        self.background = background
        self.content = content
        self.sub_response = sub_response
        self.jsonalize = jsonalize
        self.create_http_response = create_http_response

    async def __call__(self, scope, receive, send) -> None:
        assert isinstance(send, JsonRpcFutre)
        await send(
            self.content,
            self.background,
            self.sub_response,
            self.jsonalize,
            self.create_http_response,
        )
        # else:
        # TODO: background
        #     raise NotImplementedError()
        #     await send()
        #     if self.background is not None:
        #         await self.background()


class JsonRpcFutre(asyncio.Future):
    def __init__(self, rpc=None, *, loop=None):
        super().__init__(loop=loop)
        self.rpc = rpc

    async def __call__(
        self, value, background, sub_response, jsonalize, create_http_response
    ):
        if self.done():
            raise RuntimeError()
        self.set_result(
            (value, background, sub_response, jsonalize, create_http_response)
        )

    async def send_rpc_response(self, scope, receive, send):
        (
            raw_response,
            background,
            sub_response,
            jsonalize,
            create_http_response,
        ) = await self
        rpc_response = RpcResponse(result=raw_response, id=self.rpc.id)
        jsonalized = await jsonalize(rpc_response)
        response = create_http_response(jsonalized, background, sub_response)
        await response(scope, receive, send)
