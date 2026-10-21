"""TEST ONLY: fixed vectors for startup probes; no outbound HTTP or real keys."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

state = {"dimensions": 1024, "embedding_requests": 0}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Do not log headers, tokens or input texts.

    def respond(self, status, payload):
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path in ("/health", "/stats"):
            self.respond(200, {"test_double": True, **state})
        else:
            self.respond(404, {"error": "test endpoint not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        if not 0 < length <= 65536:
            self.respond(400, {"error": "invalid body length"})
            return
        try:
            body = json.loads(self.rfile.read(length))
            if self.path == "/dimensions":
                dimensions = body["dimensions"]
                if dimensions not in (768, 1024):
                    raise ValueError("unsupported test dimension")
                state["dimensions"] = dimensions
                self.respond(200, {"test_double": True, **state})
            elif self.path == "/v1/embeddings":
                inputs = body["input"]
                inputs = [inputs] if isinstance(inputs, str) else inputs
                if not isinstance(inputs, list) or not 1 <= len(inputs) <= 100:
                    raise ValueError("invalid test inputs")
                state["embedding_requests"] += 1
                self.respond(
                    200,
                    {
                        "object": "list",
                        "model": "smoke-fixed-vector",
                        "data": [
                            {
                                "object": "embedding",
                                "index": i,
                                "embedding": [1.0] + [0.0] * (state["dimensions"] - 1),
                            }
                            for i in range(len(inputs))
                        ],
                        "usage": {"prompt_tokens": 0, "total_tokens": 0},
                    },
                )
            else:
                self.respond(404, {"error": "test endpoint not found"})
        except (ValueError, KeyError, TypeError):
            self.respond(400, {"error": "invalid test request"})


if __name__ == "__main__":
    print("TEST DOUBLE: fixed vectors only; not a semantic model", flush=True)
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
