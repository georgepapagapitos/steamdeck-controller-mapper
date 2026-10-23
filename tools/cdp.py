#!/usr/bin/env python3
"""A small Chrome DevTools Protocol client for Steam's CEF debugger, stdlib only. It runs on the Deck (port 8080 is
Steam's, on localhost) and drives the map-helper plugin during development. tools/deck.sh ships it and runs it.

  cdp.py targets                          the pages Steam's CEF has open (title and url)
  cdp.py eval JS [--target T]             evaluate JS (awaited) and print the result as JSON
  cdp.py shot OUT.png [--target T]        screenshot a page; OUT "-" writes the PNG to stdout
  cdp.py reload [--plugin map-helper]     restart the plugin's backend and re-import its frontend
  cdp.py nav PATH                         navigate Steam's UI to a route, e.g. /map-helper/map

T is a substring of the page title (case-insensitive). eval, reload and nav default to SharedJSContext, where Decky
lives; shot defaults to the Big Picture page.

Decky 3.3.0 sources (@ 00cd202): `loader/reload_plugin` puts the plugin on the reload queue, which stops and starts
its backend and then emits `loader/import_plugin` to the frontend (backend/decky_loader/loader.py
handle_plugin_backend_reload, import_plugin, dispatch_plugin); `window.DeckyBackend` is the frontend's WSRouter and
`window.DFL` is @decky/ui (frontend/src/index.ts).
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import socket
import struct
import sys
import urllib.request
from urllib.parse import urlparse

HOST, PORT = "127.0.0.1", int(os.environ.get("CDP_PORT", "8080"))   # CDP_PORT: a local Chrome, for testing


def pages() -> list:
    with urllib.request.urlopen(f"http://{HOST}:{PORT}/json", timeout=5) as r:
        return [p for p in json.load(r) if p.get("webSocketDebuggerUrl")]


def find(title: str) -> dict:
    found = [p for p in pages() if title.lower() in p.get("title", "").lower()]
    if not found:
        sys.exit(f"no page with {title!r} in its title (try: cdp.py targets)")
    return found[0]


class Socket:
    """Just enough RFC 6455: text frames out (masked, as a client must), whole messages in."""

    def __init__(self, url: str):
        u = urlparse(url)
        self.sock = socket.create_connection((u.hostname, u.port or 80), timeout=30)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((f"GET {u.path} HTTP/1.1\r\nHost: {u.hostname}:{u.port}\r\nUpgrade: websocket\r\n"
                           f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n")
                          .encode())
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = self.sock.recv(1)
            if not chunk:
                sys.exit("the debugger closed the connection during the handshake")
            head += chunk
        status = head.split(b"\r\n", 1)[0].decode(errors="replace")
        if " 101 " not in status:
            sys.exit(f"websocket handshake refused: {status}")
        self.next_id = 0

    def _read(self, n: int) -> bytes:
        data = b""
        while len(data) < n:
            chunk = self.sock.recv(n - len(data))
            if not chunk:
                raise ConnectionError("the debugger closed the connection")
            data += chunk
        return data

    def send(self, text: str) -> None:
        data, mask = text.encode(), os.urandom(4)
        n = len(data)
        head = bytes([0x81]) + (bytes([0x80 | n]) if n < 126 else
                                bytes([0x80 | 126]) + struct.pack(">H", n) if n < 65536 else
                                bytes([0x80 | 127]) + struct.pack(">Q", n))
        self.sock.sendall(head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def receive(self) -> str:
        message = b""
        while True:
            b0, b1 = self._read(2)
            n = b1 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read(8))[0]
            payload = self._read(n)
            opcode = b0 & 0x0F
            if opcode == 8:
                raise ConnectionError("the debugger closed the connection")
            if opcode in (0, 1, 2):
                message += payload
                if b0 & 0x80:
                    return message.decode()

    def call(self, method: str, **params) -> dict:
        self.next_id += 1
        self.send(json.dumps({"id": self.next_id, "method": method, "params": params}))
        while True:
            reply = json.loads(self.receive())
            if reply.get("id") == self.next_id:
                if "error" in reply:
                    sys.exit(f"{method}: {reply['error'].get('message')}")
                return reply["result"]


def evaluate(title: str, js: str):
    result = Socket(find(title)["webSocketDebuggerUrl"]).call(
        "Runtime.evaluate", expression=js, awaitPromise=True, returnByValue=True, replMode=True)
    if "exceptionDetails" in result:
        details = result["exceptionDetails"]
        sys.exit(f"JS error: {details.get('exception', {}).get('description') or details.get('text')}")
    return result["result"].get("value")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="cdp.py", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("targets")
    p = sub.add_parser("eval")
    p.add_argument("js")
    p.add_argument("--target", default="SharedJSContext")
    p = sub.add_parser("shot")
    p.add_argument("out")
    p.add_argument("--target", default="Big Picture")
    p = sub.add_parser("reload")
    p.add_argument("--plugin", default="map-helper")
    p = sub.add_parser("nav")
    p.add_argument("path")
    args = parser.parse_args(argv)

    if args.command == "targets":
        for page in pages():
            print(f"{page.get('title', '')!r:40} {page.get('url', '')}")
    elif args.command == "eval":
        print(json.dumps(evaluate(args.target, args.js), indent=2))
    elif args.command == "shot":
        data = base64.b64decode(Socket(find(args.target)["webSocketDebuggerUrl"])
                                .call("Page.captureScreenshot", format="png")["data"])
        if args.out == "-":
            sys.stdout.buffer.write(data)
        else:
            with open(args.out, "wb") as f:
                f.write(data)
    elif args.command == "reload":
        evaluate("SharedJSContext", f"DeckyBackend.call('loader/reload_plugin', {json.dumps(args.plugin)})")
        print(f"reloading {args.plugin}")
    elif args.command == "nav":
        evaluate("SharedJSContext", f"DFL.Navigation.Navigate({json.dumps(args.path)}); true")
    return 0


if __name__ == "__main__":
    sys.exit(main())
