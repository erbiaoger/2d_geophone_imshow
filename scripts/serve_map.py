#!/usr/bin/env python3
"""Serve generated map HTML files over localhost for crisp live-tile zooming.

用途:
    通过本地 HTTP 服务打开 geophone_map_live.html，避免直接双击 file:// 文件时
    浏览器拦截远程瓦片请求，从而实现 Leaflet 在线瓦片的动态高分辨率缩放。

用法:
    uv run --no-sync python scripts/serve_map.py \
        --directory outputs/changbaishan_second

    指定端口:
    uv run --no-sync python scripts/serve_map.py \
        --directory outputs/changbaishan_second \
        --port 8765

输出:
    启动后会打印本地访问地址，例如:
    http://127.0.0.1:8765/geophone_map_live.html
"""

from __future__ import annotations

import argparse
import contextlib
import http.server
import socket
from functools import partial
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Serve generated map outputs over localhost.")
    parser.add_argument(
        "--directory",
        type=Path,
        default=Path("outputs"),
        help="要提供 HTTP 服务的输出目录，默认 outputs。",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="优先使用的本地端口，默认 8765。",
    )
    return parser


def pick_port(preferred_port: int) -> int:
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", preferred_port))
            return preferred_port
        except OSError:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])


def main() -> None:
    args = build_parser().parse_args()
    directory = args.directory.resolve()
    if not directory.exists():
        raise SystemExit(f"Directory does not exist: {directory}")

    port = pick_port(args.port)
    handler = partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    print(f"Serving {directory}")
    print(f"http://127.0.0.1:{port}/")
    print(f"http://127.0.0.1:{port}/geophone_map_live.html")
    server.serve_forever()


if __name__ == "__main__":
    main()
