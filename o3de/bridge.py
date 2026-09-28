#!/usr/bin/env python3
import json
import os
import re
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

HOST = os.environ.get("O3DE_BRIDGE_HOST", "0.0.0.0")
PORT = int(os.environ.get("O3DE_BRIDGE_PORT", "9765"))

DEFAULT_ROOT = Path.cwd()
ENGINE_ROOT = Path(os.environ.get("O3DE_ROOT", DEFAULT_ROOT)).expanduser().resolve()
O3DE_SCRIPT = Path(
    os.environ.get("O3DE_SCRIPT", ENGINE_ROOT / "scripts" / "o3de.py")
).expanduser().resolve()
WORKSPACE_ROOT = Path(
    os.environ.get("O3DE_WORKSPACE_ROOT", ENGINE_ROOT)
).expanduser().resolve()

COMMANDS = {
    "get-global-project",
    "set-global-project",
    "create-template",
    "create-from-template",
    "register",
    "register-show",
    "get-registered",
    "enable-gem",
    "disable-gem",
    "edit-engine-properties",
    "edit-project-properties",
    "edit-gem-properties",
    "sha256",
    "download",
    "export-project-configure",
    "export-project",
    "repo",
    "edit-repo-properties",
}


def compact(value, limit=12000):
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[-limit:]


def safe_cwd(value):
    if not value:
        return WORKSPACE_ROOT
    candidate = Path(value).expanduser().resolve()
    if candidate != WORKSPACE_ROOT and WORKSPACE_ROOT not in candidate.parents:
        raise ValueError("cwd must stay inside O3DE_WORKSPACE_ROOT")
    if not candidate.is_dir():
        raise ValueError("cwd does not exist")
    return candidate


def run_cli(command, args, cwd, timeout_seconds):
    if command not in COMMANDS:
        raise ValueError(f"Unsupported O3DE command: {command}")

    if not O3DE_SCRIPT.is_file():
        raise RuntimeError(
            f"O3DE CLI not found at {O3DE_SCRIPT}. Set O3DE_ROOT or O3DE_SCRIPT."
        )

    if not isinstance(args, list) or len(args) > 64:
        raise ValueError("args must be a list with at most 64 items")

    clean_args = []
    for value in args:
        if not isinstance(value, str):
            raise ValueError("Every O3DE CLI argument must be a string")
        if "\x00" in value:
            raise ValueError("NUL bytes are not allowed")
        if len(value) > 512:
            raise ValueError("An O3DE CLI argument is longer than 512 characters")
        clean_args.append(value)

    timeout_seconds = max(1, min(int(timeout_seconds or 120), 300))
    workdir = safe_cwd(cwd)

    completed = subprocess.run(
        [sys.executable, str(O3DE_SCRIPT), command, *clean_args],
        cwd=str(workdir),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout_seconds,
        check=False,
        shell=False,
    )

    return {
        "status": "ok" if completed.returncode == 0 else "failed",
        "command": command,
        "args": clean_args,
        "cwd": str(workdir),
        "returnCode": completed.returncode,
        "stdout": compact(completed.stdout),
        "stderr": compact(completed.stderr),
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "HyoukaO3DEBridge/1.0"

    def send_json(self, status, payload):
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        try:
            if path == "/health":
                self.send_json(
                    200,
                    {
                        "status": "ok",
                        "engine": "O3DE",
                        "engineRoot": str(ENGINE_ROOT),
                        "o3deScript": str(O3DE_SCRIPT),
                        "configured": O3DE_SCRIPT.is_file(),
                        "commands": sorted(COMMANDS),
                        "workspaceRoot": str(WORKSPACE_ROOT),
                    },
                )
                return

            if path == "/commands":
                self.send_json(200, {"commands": sorted(COMMANDS)})
                return

            self.send_json(404, {"status": "error", "error": "not_found"})
        except Exception as exc:
            self.send_json(
                500,
                {"status": "error", "error": type(exc).__name__, "message": str(exc)},
            )

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length else b"{}"
            payload = json.loads(raw.decode("utf-8"))

            if path == "/help":
                topic = str(payload.get("topic", "")).strip()
                args = ["--help"] if not topic else [topic, "--help"]
                result = subprocess.run(
                    [sys.executable, str(O3DE_SCRIPT), *args],
                    cwd=str(WORKSPACE_ROOT),
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=30,
                    check=False,
                    shell=False,
                )
                self.send_json(
                    200,
                    {
                        "status": "ok" if result.returncode == 0 else "failed",
                        "returnCode": result.returncode,
                        "stdout": compact(result.stdout),
                        "stderr": compact(result.stderr),
                    },
                )
                return

            if path == "/cli":
                result = run_cli(
                    str(payload.get("command", "")),
                    payload.get("args", []),
                    payload.get("cwd"),
                    payload.get("timeoutSeconds", 120),
                )
                self.send_json(200 if result["status"] == "ok" else 400, result)
                return

            self.send_json(404, {"status": "error", "error": "not_found"})
        except subprocess.TimeoutExpired as exc:
            self.send_json(
                408,
                {
                    "status": "timeout",
                    "error": "command_timeout",
                    "stdout": compact(exc.stdout),
                    "stderr": compact(exc.stderr),
                },
            )
        except Exception as exc:
            self.send_json(
                400,
                {"status": "error", "error": type(exc).__name__, "message": str(exc)},
            )

    def log_message(self, format_string, *args):
        return


if __name__ == "__main__":
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
