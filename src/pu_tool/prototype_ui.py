"""PROTOTYPE (throwaway) — 三个选活动/待办前端变体，?variant= 切换。

Three variants of 选活动+待办, switchable via ?variant=.
Run: uv run python -m pu_tool.prototype_ui
Then open http://127.0.0.1:8765/?variant=A
"""

from __future__ import annotations

import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST = "127.0.0.1"
PORT = 8765
HTML = Path(__file__).with_name("prototype_ui.html")


class _Handler(SimpleHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path.split("?", 1)[0] in {"/", "/prototype/ui", "/prototype/ui.html"}:
            data = HTML.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return
        self.send_error(404, "prototype only serves /")

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        print(f"[prototype-ui] {args[0]}")


def serve(port: int = PORT, open_browser: bool = True) -> None:
    print("PROTOTYPE throwaway — 选活动/待办前端效果，不接 PU。")
    print("A 英雄缺口  B 左右分栏  C 三列流水线")
    print(f"http://{HOST}:{port}/?variant=A")
    httpd = ThreadingHTTPServer((HOST, port), _Handler)
    if open_browser:
        webbrowser.open(f"http://{HOST}:{port}/?variant=A")
    httpd.serve_forever()


if __name__ == "__main__":
    serve()
