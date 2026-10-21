"""TEST ONLY loopback ingress for the isolated startup harness, not a gateway product.

Fixed API/web upstreams only: no CONNECT, absolute URLs or arbitrary destinations.
No credentials, bodies or headers are logged. Not designed for streaming/SSE.
"""

from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

HOP_HEADERS = {
    "connection",
    "transfer-encoding",
    "keep-alive",
    "te",
    "trailer",
    "upgrade",
    "proxy-authenticate",
    "proxy-authorization",
    "content-length",
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def forward(self):
        if not self.path.startswith("/"):
            self.send_error(400, "Only origin-form paths are accepted")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_error(400)
            return
        if not 0 <= length <= 1048576:
            self.send_error(413)
            return
        body = self.rfile.read(length) if length else None
        headers = {
            k: v for k, v in self.headers.items() if k.lower() not in HOP_HEADERS
        }
        connection = HTTPConnection(*self.server.upstream, timeout=10)
        try:
            connection.request(self.command, self.path, body=body, headers=headers)
            response = connection.getresponse()
            data = response.read()
            self.send_response(response.status)
            for name, value in response.getheaders():
                if name.lower() not in HOP_HEADERS:
                    self.send_header(name, value)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except OSError:
            self.send_error(502, "Test upstream unavailable")
        finally:
            connection.close()

    do_GET = forward
    do_POST = forward
    do_OPTIONS = forward


def make_server(port, upstream, host="0.0.0.0"):
    server = ThreadingHTTPServer((host, port), Handler)
    server.upstream = upstream
    return server


if __name__ == "__main__":
    api = make_server(8081, ("api", 8000))
    Thread(target=api.serve_forever, daemon=True).start()
    print(
        "TEST ONLY ingress: fixed API/web upstreams; publish on loopback only",
        flush=True,
    )
    make_server(8082, ("web", 3000)).serve_forever()
