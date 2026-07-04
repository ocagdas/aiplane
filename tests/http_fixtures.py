from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


class OpenAICompatibleTestHandler(BaseHTTPRequestHandler):
    model_id = "test-model"

    def do_GET(self) -> None:
        if self.path == "/v1/models":
            self._json({"data": [{"id": self.model_id}]})
            return
        self.send_error(404)

    def do_POST(self) -> None:
        if self.path == "/v1/chat/completions":
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            self._json({"choices": [{"message": {"content": f"handled {body['model']}"}}]})
            return
        self.send_error(404)

    def log_message(self, format: str, *args: object) -> None:
        return

    def _json(self, payload: dict[str, object]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class TestHttpServer:
    def __enter__(self) -> str:
        self.server = HTTPServer(("127.0.0.1", 0), OpenAICompatibleTestHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address
        return f"http://{host}:{port}/v1"

    def __exit__(self, exc_type, exc, tb) -> None:
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()


__all__ = ["OpenAICompatibleTestHandler", "TestHttpServer"]
