import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from django.urls import path
from runner.consumers import CodeRunnerConsumer

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "code_runner_proj.settings")

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": URLRouter([
        path("ws/run-code/", CodeRunnerConsumer.as_asgi()),
    ]),
})
