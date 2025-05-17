import json
import docker
import asyncio
import uuid
import os
import threading
from channels.generic.websocket import AsyncWebsocketConsumer
client = docker.from_env()
class CodeRunnerConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.accept()
        self.container = None
        self.sock = None
        self.loop = asyncio.get_running_loop()

    async def close(self, close_code):
        if self.container:
            try:
                self.container.kill()
                self.container.remove(force=True)
            except:
                pass
        if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
            try:
                os.remove(os.path.join(self.temp_dir, "script.py"))
                os.rmdir(self.temp_dir)
            except:
                pass

    async def receive(self, text_data):
        data = json.loads(text_data)
        action = data.get("action")

        if action == "start":
            code = data.get("code", "")
            await self.start_container(code)

        elif action == "input":
            user_input = data.get("input", "") + "\n"
            await self.send_input(user_input)

    async def send_input(self, user_input):
        if self.container and self.sock:
            try:
                self.sock._sock.send(user_input.encode())
            except Exception as e:
                await self.send(text_data=json.dumps({
                    "action": "error",
                    "message": f"Failed to send input: {str(e)}"
                }))

    async def start_container(self, code):
        self.temp_dir = f"/tmp/{uuid.uuid4()}"
        os.makedirs(self.temp_dir, exist_ok=True)
        script_path = os.path.join(self.temp_dir, "script.py")
        with open(script_path, "w") as f:
            f.write(code)

        self.container = client.containers.run(
            image="python:3.10-slim",
            command=["python", "/code/script.py"],
            volumes={self.temp_dir: {'bind': '/code', 'mode': 'rw'}},
            working_dir="/code",
            stdin_open=True,
            tty=False,
            detach=True,
        )

        self.sock = self.container.attach_socket(params={'stdin': 1, 'stdout': 1, 'stderr': 1, 'stream': 1})

        def read_output():
            while True:
                try:
                    output = self.sock._sock.recv(1024)
                    if output:
                        asyncio.run_coroutine_threadsafe(self.send(text_data=json.dumps({
                            "action": "output",
                            "output": output.decode(errors="ignore")
                        })), self.loop)
                    else:
                        asyncio.run_coroutine_threadsafe(self.send(text_data=json.dumps({
                            "action": "done"
                        })), self.loop)
                        asyncio.run_coroutine_threadsafe(self.close(200), self.loop)
                        break
                except Exception:
                    break

        threading.Thread(target=read_output, daemon=True).start()

        def timeout_watchdog():
            try:
                self.container.wait(timeout=8)
            except Exception as e :
                asyncio.run_coroutine_threadsafe(self.send(text_data=json.dumps({
                    "action": "output",
                    "output": "Execution stopped: Time limit of 8 seconds exceeded.\n"
                })), self.loop)
                asyncio.run_coroutine_threadsafe(asyncio.sleep(0.1), self.loop)
                asyncio.run_coroutine_threadsafe(self.close(200), self.loop)
                self.container.kill()
            except Exception as e:
                asyncio.run_coroutine_threadsafe(self.send(text_data=json.dumps({
                    "action": "output",
                    "output": f"Execution stopped: {str(e)}\n"
                })), self.loop)
                asyncio.run_coroutine_threadsafe(asyncio.sleep(0.1), self.loop)
                asyncio.run_coroutine_threadsafe(self.close(200), self.loop)
                self.container.kill()

        threading.Thread(target=timeout_watchdog, daemon=True).start()
