#!/usr/bin/env python3
import json
import os
import re
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HOST = os.environ.get("O3DE_BRIDGE_HOST", "0.0.0.0")
PORT = int(os.environ.get("O3DE_BRIDGE_PORT", "9765"))
ENGINE_ROOT = Path(os.environ.get("O3DE_ROOT", "/opt/O3DE/26.05")).expanduser().resolve()
WORKSPACE_ROOT = Path(os.environ.get("O3DE_WORKSPACE_ROOT", Path.cwd())).expanduser().resolve()
O3DE_CLI = ENGINE_ROOT / "scripts" / "o3de.sh"
O3DE_PY = ENGINE_ROOT / "scripts" / "o3de.py"
MAX_ARGS = 128
MAX_ARG_LENGTH = 4096
MAX_OUTPUT = 20000
COMMAND_FALLBACKS = {
    "get-global-project", "set-global-project", "create-template",
    "create-from-template", "register", "register-show", "get-registered",
    "enable-gem", "disable-gem", "edit-engine-properties",
    "edit-project-properties", "edit-gem-properties", "sha256", "download",
    "export-project-configure", "export-project", "repo",
    "edit-repo-properties",
}

def compact(value, limit=MAX_OUTPUT):
    text = str(value or "")
    return text if len(text) <= limit else text[-limit:]

def inside_workspace(value):
    if not value:
        return WORKSPACE_ROOT
    path = Path(value).expanduser().resolve()
    try:
        path.relative_to(WORKSPACE_ROOT)
    except ValueError:
        raise ValueError("cwd must stay inside O3DE_WORKSPACE_ROOT")
    if not path.is_dir():
        raise ValueError("cwd does not exist")
    return path

def validate_args(args):
    if not isinstance(args, list) or len(args) > MAX_ARGS:
        raise ValueError("args must be a list with at most 128 items")
    out = []
    for arg in args:
        if not isinstance(arg, str):
            raise ValueError("every argument must be a string")
        if "\x00" in arg or len(arg) > MAX_ARG_LENGTH:
            raise ValueError("invalid tool argument")
        out.append(arg)
    return out

def top_level_commands():
    commands = set(COMMAND_FALLBACKS)
    if O3DE_PY.is_file():
        text = O3DE_PY.read_text(encoding="utf-8", errors="ignore")
        for match in re.finditer(r"\badd_parser\s*\(\s*[\"']([^\"']+)[\"']", text):
            commands.add(match.group(1))
    return sorted(commands)

def run_cli(command, args, cwd=None, timeout=120):
    if command not in top_level_commands():
        raise ValueError("command is not a first-party O3DE top-level CLI command")
    if not O3DE_CLI.is_file():
        raise RuntimeError(f"O3DE CLI not found at {O3DE_CLI}")
    clean_args = validate_args(args)
    workdir = inside_workspace(cwd)
    timeout = max(1, min(int(timeout or 120), 300))
    proc = subprocess.run(
        [str(O3DE_CLI), command, *clean_args],
        cwd=str(workdir),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
        shell=False,
        check=False,
        env={**os.environ, "O3DE_ROOT": str(ENGINE_ROOT), "O3DE_WORKSPACE_ROOT": str(WORKSPACE_ROOT)},
    )
    return {
        "status": "ok" if proc.returncode == 0 else "failed",
        "engine": "O3DE",
        "kind": "o3de-cli",
        "toolId": f"o3de-cli:{command}",
        "returnCode": proc.returncode,
        "stdout": compact(proc.stdout),
        "stderr": compact(proc.stderr),
        "cwd": str(workdir),
    }

def discover():
    commands = top_level_commands()
    tools = [
        {
            "id": f"o3de-cli:{command}",
            "kind": "o3de-cli",
            "name": command,
            "path": str(O3DE_PY.relative_to(ENGINE_ROOT)).replace(os.sep, "/"),
            "callable": True,
            "source": "O3DE first-party top-level CLI",
        }
        for command in commands
    ]
    return {
        "status": "ok",
        "engine": "O3DE",
        "engineRoot": str(ENGINE_ROOT),
        "workspaceRoot": str(WORKSPACE_ROOT),
        "toolCount": len(tools),
        "byKind": {"o3de-cli": len(tools)},
        "tools": tools,
        "secureMode": "public-cli-only",
    }

class Handler(BaseHTTPRequestHandler):
    server_version = "HyoukaO3DEPublicBridge/1.0"

    def send_json(self, code, payload):
        body = json.dumps(payload, separators=(",", ":")).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        size = int(self.headers.get("Content-Length", "0"))
        if size > 200000:
            raise ValueError("request body too large")
        return json.loads(self.rfile.read(size).decode("utf-8") if size else "{}")

    def do_GET(self):
        path = urlparse(self.path).path
        try:
            if path == "/health":
                self.send_json(200, {
                    "status": "ok",
                    "engine": "O3DE",
                    "bridgeMode": "public-cli-only",
                    "engineRoot": str(ENGINE_ROOT),
                    "o3deCli": str(O3DE_CLI),
                    "o3deScript": str(O3DE_PY),
                    "toolCount": len(top_level_commands()),
                    "commands": top_level_commands(),
                })
                return
            if path == "/discover":
                self.send_json(200, discover())
                return
            if path == "/find":
                query = parse_qs(urlparse(self.path).query).get("q", [""])[0].lower()
                tools = [t for t in discover()["tools"] if query in json.dumps(t).lower()]
                self.send_json(200, {**discover(), "tools": tools, "returnedTools": len(tools)})
                return
            self.send_json(404, {"status": "error", "error": "not_found"})
        except Exception as exc:
            self.send_json(500, {"status": "error", "error": type(exc).__name__, "message": str(exc)})

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            payload = self.read_json()
            if path == "/cli":
                command = str(payload.get("command", "")).strip()
                if payload.get("background"):
                    raise ValueError("background execution is disabled in public-cli-only mode")
                self.send_json(200, run_cli(command, payload.get("args", []), payload.get("cwd"), payload.get("timeoutSeconds", 120)))
                return
            if path == "/invoke":
                tool_id = str(payload.get("toolId", "")).strip()
                if not tool_id.startswith("o3de-cli:"):
                    self.send_json(403, {
                        "status": "forbidden",
                        "error": "public bridge allows only first-party O3DE CLI tools",
                        "hint": "Configure O3DE_BRIDGE_TOKEN on both sides to enable universal tool execution.",
                    })
                    return
                command = tool_id[len("o3de-cli:"):]
                if payload.get("background"):
                    raise ValueError("background execution is disabled in public-cli-only mode")
                self.send_json(200, run_cli(command, payload.get("args", []), payload.get("cwd"), payload.get("timeoutSeconds", 120)))
                return
            if path == "/help":
                topic = str(payload.get("topic", "")).strip()
                args = ["--help"] if not topic else [topic, "--help"]
                result = run_cli(args[0] if topic else "__root_help__", args[1:] if topic else [], payload.get("cwd"), 30) if topic else subprocess.run(
                    [str(O3DE_CLI), "--help"],
                    cwd=str(inside_workspace(payload.get("cwd"))),
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=30,
                    shell=False,
                    check=False,
                )
                if topic:
                    self.send_json(200, result)
                else:
                    self.send_json(200, {
                        "status": "ok" if result.returncode == 0 else "failed",
                        "returnCode": result.returncode,
                        "stdout": compact(result.stdout),
                        "stderr": compact(result.stderr),
                    })
                return
            self.send_json(404, {"status": "error", "error": "not_found"})
        except subprocess.TimeoutExpired:
            self.send_json(408, {"status": "timeout", "error": "command_timeout"})
        except Exception as exc:
            self.send_json(400, {"status": "error", "error": type(exc).__name__, "message": str(exc)})

    def log_message(self, *_):
        return

if __name__ == "__main__":
    if not ENGINE_ROOT.exists():
        raise SystemExit(f"O3DE_ROOT does not exist: {ENGINE_ROOT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
