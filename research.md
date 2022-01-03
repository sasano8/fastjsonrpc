# ルーティング・実行の仕組み

1. APIRouterによってパスマッチングされる
2. APIRoute.handleでリクエストに対して応答能力を備えているか検証する
3. request_responseでリクエストが実行される
4. fastapi.routing.get_request_handlerでpydanticによる検証や依存性解決など独自処理が実行される

# ディスパッチを実現するには

1. APIRouterによってパスがマッチングされる
2. マッチしたパスがエントリーポイントなら、リクエストのパスを書き換え再度APIRouterにマッチングをお願いする
3. メソッドにリクエストが届いたら、エントリーポイント経由（フラグを立てておく）ならJSONRPCとして処理し、
    そうでないなら、単にFastAPIに処理をお願いする。

# バッチ処理を実現するには


# ウェブソケットからディスパッチを実現するには


# スタックトレース

``` python
FastAPI.__call__(self, scope: Scope, receive: Receive, send: Send):
    if self.root_path:
            scope["root_path"] = self.root_path
        if AsyncExitStack:
            async with AsyncExitStack() as stack:
                scope["fastapi_astack"] = stack
                await super().__call__(scope, receive, send)
        else:
            await super().__call__(scope, receive, send)  # pragma: no cover


Starlette.__call__(self, scope: Scope, receive: Receive, send: Send):
    scope["app"] = self
        await self.middleware_stack(scope, receive, send)

starlett.ServerErrorMiddleware
    if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def _send(message: Message) -> None:
            nonlocal response_started, send

            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, _send) =>>>>
        except Exception as exc:
            if not response_started:
                request = Request(scope)
                if self.debug:
                    # In debug mode, return traceback responses.
                    response = self.debug_response(request, exc)
                elif self.handler is None:
                    # Use our default 500 error handler.
                    response = self.error_response(request, exc)
                else:
                    # Use an installed 500 error handler.
                    if asyncio.iscoroutinefunction(self.handler):
                        response = await self.handler(request, exc)
                    else:
                        response = await run_in_threadpool(self.handler, request, exc)

                await response(scope, receive, send)

starlette.exceptions.ExceptionMiddleware
    if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def sender(message: Message) -> None:
            nonlocal response_started

            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, sender) ->>>>>
        except Exception as exc:
            handler = None

            if isinstance(exc, HTTPException):
                handler = self._status_handlers.get(exc.status_code)

            if handler is None:
                handler = self._lookup_exception_handler(exc)

            if handler is None:
                raise exc

            if response_started:
                msg = "Caught handled exception, but response already started."
                raise RuntimeError(msg) from exc

            request = Request(scope, receive=receive)
            if asyncio.iscoroutinefunction(handler):
                response = await handler(request, exc)
            else:
                response = await run_in_threadpool(handler, request, exc)
            await response(scope, receive, sender)

fastapi.routing.APIRouter
    assert scope["type"] in ("http", "websocket", "lifespan")

        if "router" not in scope:
            scope["router"] = self

        if scope["type"] == "lifespan":
            await self.lifespan(scope, receive, send)
            return

        partial = None

        for route in self.routes:
            # Determine if any route matches the incoming scope,
            # and hand over to the matching route if found.
            match, child_scope = route.matches(scope)
            if match == Match.FULL:
                scope.update(child_scope)
                await route.handle(scope, receive, send) ->>>>>>>>>>>>>>>
                return
            elif match == Match.PARTIAL and partial is None:
                partial = route
                partial_scope = child_scope

        if partial is not None:
            #  Handle partial matches. These are cases where an endpoint is
            # able to handle the request, but is not a preferred option.
            # We use this in particular to deal with "405 Method Not Allowed".
            scope.update(partial_scope)
            await partial.handle(scope, receive, send)
            return

        if scope["type"] == "http" and self.redirect_slashes and scope["path"] != "/":
            redirect_scope = dict(scope)
            if scope["path"].endswith("/"):
                redirect_scope["path"] = redirect_scope["path"].rstrip("/")
            else:
                redirect_scope["path"] = redirect_scope["path"] + "/"

            for route in self.routes:
                match, child_scope = route.matches(redirect_scope)
                if match != Match.NONE:
                    redirect_url = URL(scope=redirect_scope)
                    response = RedirectResponse(url=str(redirect_url))
                    await response(scope, receive, send)
                    return

        await self.default(scope, receive, send)


fastapi.routing.APIRoute
    async def handle(self, scope: Scope, receive: Receive, send: Send) -> None:
        if self.methods and scope["method"] not in self.methods:
            if "app" in scope:
                raise HTTPException(status_code=405)
            else:
                response = PlainTextResponse("Method Not Allowed", status_code=405)
            await response(scope, receive, send)
        else:
            await self.app(scope, receive, send) =>>>>>>>>>>>>>>>>>>>


# funcはfastapi.APIRoute.get_route_handlerで取得した関数
starlette.routing
def request_response(func: typing.Callable) -> ASGIApp:
    """
    Takes a function or coroutine `func(request) -> response`,
    and returns an ASGI application.
    """
    is_coroutine = iscoroutinefunction_or_partial(func)

->>>>>>>>>>    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        request = Request(scope, receive=receive, send=send)
        if is_coroutine:
            response = await func(request) ->>>>>>>>>>>>>>>>>>>
        else:
            response = await run_in_threadpool(func, request)
        await response(scope, receive, send)

    return app


fastapi.routing.get_request_handler
    get_route_handler

```

