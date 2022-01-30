# pragma: no cover

from fastapi import Depends, FastAPI, Request, WebSocket
from pydantic import BaseModel

from fastjsonrpc import JsonRpcRouter, RpcError

rpc = JsonRpcRouter()


@rpc.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    while True:
        import asyncio

        global rpc
        rpc = rpc.get_websocket(websocket)

        while True:
            res = await rpc.post(
                {
                    "jsonrpc": "2.0",
                    "method": "echo",
                    "params": {"msg": "hello"},
                    "id": 0,
                }
            )
            await websocket.send_json(res)
            await asyncio.sleep(1)


def get_suffix():
    return "!!!"


@rpc.post()
class Echo(BaseModel):
    msg: str = "hello"

    def __call__(self, suffix: str = Depends(get_suffix)):
        return self.msg + suffix


@rpc.post()
class Error(BaseModel):
    msg: str = "error occured."

    def __call__(self):
        raise YourAppError(self.msg)


@rpc.post()
class Empty(BaseModel):
    def __call__(self):
        return ""


class YourAppError(RpcError):
    code = -32001  # -32001, -32002, ...
    message = "Application exception."


app = FastAPI()
app.include_router(rpc, prefix="/jsonrpc")


from fastapi.responses import HTMLResponse

html = """
<!DOCTYPE html>
<html>
    <head>
        <title>Chat</title>
    </head>
    <body>
        <h1>WebSocket Chat</h1>
        <form action="" onsubmit="sendMessage(event)">
            <input type="text" id="messageText" autocomplete="off"/>
            <button>Send</button>
        </form>
        <ul id='messages'>
        </ul>
        <script>
            var ws = new WebSocket("%(ws_endpoint)s");
            ws.onmessage = function(event) {
                var messages = document.getElementById('messages')
                var message = document.createElement('li')
                var content = document.createTextNode(event.data)
                message.appendChild(content)
                messages.appendChild(message)
            };
            function sendMessage(event) {
                var input = document.getElementById("messageText")
                ws.send(input.value)
                input.value = ''
                event.preventDefault()
            }
        </script>
    </body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def get(request: Request):
    url = request.base_url
    _ = html % {"ws_endpoint": "ws://localhost:8000/jsonrpc/ws"}
    return _
