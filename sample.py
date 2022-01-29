from fastapi import Depends, FastAPI
from pydantic import BaseModel

from fastjsonrpc import JsonRpcRouter, RpcError

rpc = JsonRpcRouter()


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


from fastapi import WebSocket
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
            var ws = new WebSocket("ws://localhost:8000/ws");
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


@app.get("/")
async def get():
    return HTMLResponse(html)


def get_hello():
    return "hello"


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, text: str = Depends(get_hello)):
    await websocket.accept()
    await websocket.send_text(text)
    while True:
        data = await websocket.receive_text()
        await websocket.send_text(f"Message text was: {data}")

    """
    state
        "_state"への参照を設定すれば、websocketの状態をディスパッチ先のメソッドに連携できる
        if not hasattr(self, "_state"):
            self._state = State(self.scope["state"])
    """
