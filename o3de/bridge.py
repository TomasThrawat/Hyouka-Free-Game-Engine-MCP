#!/usr/bin/env python3
import argparse
import json
import os
import re
import signal
import stat
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
BUILD_ROOT = Path(
    os.environ.get("O3DE_BUILD_DIR", ENGINE_ROOT / "build")
).expanduser().resolve()
BRIDGE_TOKEN = os.environ.get("O3DE_BRIDGE_TOKEN", "").strip()

TOP_LEVEL_COMMANDS = {
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

SCAN_ROOT_NAMES = (
    "scripts",
    "Tools",
    "Code/Tools",
    "AutomatedTesting",
    "Gems",
    "python",
    "cmake",
    "build",
    "bin",
    "install",
)

EXCLUDED_PARTS = {
    ".git",
    "3rdParty",
    "node_modules",
    "__pycache__",
    ".cache",
    "Cache",
    "CacheFiles",
    "Intermediate",
}

MAX_DISCOVERED_TOOLS = 1000
MAX_HELP_OUTPUT = 16000
MAX_RESULT_OUTPUT = 20000
MAX_ARGS = 128

BACKGROUND_PROCESSES = {}


def compact(value, limit=MAX_RESULT_OUTPUT):
    text = str(value or "")
    return text if len(text) <= limit else text[-limit:]


def is_relative_to(path, root):
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def inside_engine(path):
    return is_relative_to(path.resolve(), ENGINE_ROOT)


def safe_workspace_path(value):
    if not value:
        return WORKSPACE_ROOT
    candidate = Path(value).expanduser().resolve()
    if not is_relative_to(candidate, WORKSPACE_ROOT):
        raise ValueError("cwd must stay inside O3DE_WORKSPACE_ROOT")
    if not candidate.is_dir():
        raise ValueError("cwd does not exist")
    return candidate


def relative_path(path):
    return str(path.resolve().relative_to(ENGINE_ROOT)).replace(os.sep, "/")


def slugify(value):
    return re.sub(r"[^a-zA-Z0-9._/-]+", "-", value.replace("\\", "/")).strip("-/")


def auth_ok(handler):
    if not BRIDGE_TOKEN:
        return True
    supplied = handler.headers.get("Authorization", "")
    return supplied == f"Bearer {BRIDGE_TOKEN}"


def reject_if_unauthorized(handler):
    if auth_ok(handler):
        return False
    handler.send_json(
        401,
        {
            "status": "unauthorized",
            "error": "A valid O3DE_BRIDGE_TOKEN is required.",
        },
    )
    return True


def excluded(path):
    return any(part in EXCLUDED_PARTS for part in path.parts)


def candidate_roots():
    roots = []
    for name in SCAN_ROOT_NAMES:
        candidate = ENGINE_ROOT / name
        if candidate.is_dir() and candidate not in roots:
            roots.append(candidate)
    if ENGINE_ROOT.is_dir():
        roots.append(ENGINE_ROOT)
    return roots


def python_is_callable(path):
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    return (
        "__main__" in text
        or "argparse" in text
        or re.search(r"(^|\n)\s*def\s+main\s*\(", text) is not None
    )


def executable_file(path):
    try:
        mode = path.stat().st_mode
    except OSError:
        return False
    return bool(mode & stat.S_IXUSR) and path.is_file()


def parse_cmake_targets(path):
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    targets = []
    pattern = re.compile(
        r"\b(add_executable|add_custom_target)\s*\(\s*([A-Za-z0-9_.:+-]+)",
        re.IGNORECASE,
    )
    for match in pattern.finditer(text):
        targets.append((match.group(1).lower(), match.group(2)))
    return targets


def discover_tools():
    tools = {}
    visited = set()

    def add_tool(tool):
        key = tool["id"]
        if key not in tools and len(tools) < MAX_DISCOVERED_TOOLS:
            tools[key] = tool

    for root in candidate_roots():
        try:
            walker = os.walk(root)
        except OSError:
            continue
        for current, dirs, files in walker:
            current_path = Path(current)
            dirs[:] = [
                d for d in dirs
                if d not in EXCLUDED_PARTS
                and not d.startswith(".")
            ]
            if str(current_path) in visited:
                continue
            visited.add(str(current_path))

            for filename in files:
                path = current_path / filename
                if excluded(path) or not path.is_file():
                    continue

                rel = relative_path(path)
                lower = filename.lower()

                if lower.endswith(".py") and python_is_callable(path):
                    add_tool(
                        {
                            "id": f"py:{slugify(rel)}",
                            "kind": "python",
                            "name": path.stem,
                            "path": rel,
                            "call": [sys.executable, str(path)],
                            "callable": True,
                            "source": "O3DE Python/script tree",
                        }
                    )
                    continue

                if lower.endswith(".sh") and (
                    "/scripts/" in f"/{rel}" or "/tools/" in f"/{rel.lower()}"
                ):
                    add_tool(
                        {
                            "id": f"sh:{slugify(rel)}",
                            "kind": "shell-script",
                            "name": path.stem,
                            "path": rel,
                            "call": ["bash", str(path)],
                            "callable": True,
                            "source": "O3DE script/tool tree",
                        }
                    )
                    continue

                if os.name == "nt" and lower.endswith((".exe", ".cmd", ".bat")):
                    add_tool(
                        {
                            "id": f"exe:{slugify(rel)}",
                            "kind": "executable",
                            "name": path.stem,
                            "path": rel,
                            "call": [str(path)],
                            "callable": True,
                            "source": "O3DE built tool tree",
                        }
                    )
                    continue

                if os.name != "nt" and executable_file(path):
                    add_tool(
                        {
                            "id": f"exe:{slugify(rel)}",
                            "kind": "executable",
                            "name": path.stem,
                            "path": rel,
                            "call": [str(path)],
                            "callable": True,
                            "source": "O3DE built tool tree",
                        }
                    )
                    continue

                if lower == "cmakelists.txt":
                    for target_kind, target in parse_cmake_targets(path):
                        add_tool(
                            {
                                "id": f"cmake:{slugify(rel)}:{slugify(target)}",
                                "kind": "cmake-target",
                                "name": target,
                                "path": rel,
                                "target": target,
                                "targetKind": target_kind,
                                "callable": True,
                                "source": "O3DE CMake tool target",
                            }
                        )

    for command in sorted(TOP_LEVEL_COMMANDS):
        if O3DE_SCRIPT.is_file():
            add_tool(
                {
                    "id": f"o3de-cli:{command}",
                    "kind": "o3de-cli",
                    "name": command,
                    "path": relative_path(O3DE_SCRIPT),
                    "call": [sys.executable, str(O3DE_SCRIPT), command],
                    "callable": True,
                    "source": "O3DE scripts/o3de.py top-level CLI",
                }
            )

    return sorted(tools.values(), key=lambda item: item["id"])


def tool_index():
    return {item["id"]: item for item in discover_tools()}


def validate_args(args):
    if not isinstance(args, list) or len(args) > MAX_ARGS:
        raise ValueError(f"args must be a list with at most {MAX_ARGS} items")
    clean = []
    for value in args:
        if not isinstance(value, str):
            raise ValueError("Every tool argument must be a string")
        if "\x00" in value:
            raise ValueError("NUL bytes are not allowed")
        if len(value) > 4096:
            raise ValueError("A tool argument is longer than 4096 characters")
        clean.append(value)
    return clean


def command_for_tool(tool, args):
    if tool["kind"] in {"python", "shell-script", "executable", "o3de-cli"}:
        return tool["call"] + args

    if tool["kind"] == "cmake-target":
        build_root = BUILD_ROOT
        if not build_root.is_dir():
            raise RuntimeError(
                f"O3DE build directory not found at {build_root}. "
                "Set O3DE_BUILD_DIR to a configured CMake build tree."
            )
        return ["cmake", "--build", str(build_root), "--target", tool["target"], *args]

    raise ValueError(f"Unsupported tool kind: {tool['kind']}")


def run_tool(tool_id, args, cwd, timeout_seconds, background=False):
    index = tool_index()
    tool = index.get(tool_id)
    if not tool:
        raise ValueError(
            "Unknown tool_id. Call /discover first and use an id from the returned inventory."
        )

    if not tool.get("callable", False):
        raise ValueError("The selected inventory entry is not callable")

    clean_args = validate_args(args)
    workdir = safe_workspace_path(cwd)
    timeout_seconds = max(1, min(int(timeout_seconds or 120), 600))
    command = command_for_tool(tool, clean_args)

    environment = os.environ.copy()
    environment["O3DE_ROOT"] = str(ENGINE_ROOT)
    environment["O3DE_WORKSPACE_ROOT"] = str(WORKSPACE_ROOT)
    environment["O3DE_BUILD_DIR"] = str(BUILD_ROOT)

    if background:
        process = subprocess.Popen(
            command,
            cwd=str(workdir),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=False,
            start_new_session=(os.name != "nt"),
            env=environment,
        )
        BACKGROUND_PROCESSES[process.pid] = process
        return {
            "status": "started",
            "toolId": tool_id,
            "kind": tool["kind"],
            "command": command[0],
            "args": command[1:],
            "cwd": str(workdir),
            "pid": process.pid,
        }

    completed = subprocess.run(
        command,
        cwd=str(workdir),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout_seconds,
        shell=False,
        check=False,
        env=environment,
    )

    return {
        "status": "ok" if completed.returncode == 0 else "failed",
        "toolId": tool_id,
        "kind": tool["kind"],
        "path": tool["path"],
        "returnCode": completed.returncode,
        "stdout": compact(completed.stdout),
        "stderr": compact(completed.stderr),
        "cwd": str(workdir),
    }


def probe_tool(tool_id):
    index = tool_index()
    tool = index.get(tool_id)
    if not tool:
        raise ValueError("Unknown tool_id")
    if tool["kind"] == "cmake-target":
        raise ValueError("CMake targets are build targets, not directly probeable")

    command = command_for_tool(tool, ["--help"])
    try:
        completed = subprocess.run(
            command,
            cwd=str(WORKSPACE_ROOT),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
            shell=False,
            check=False,
        )
        return {
            "status": "ok" if completed.returncode == 0 else "failed",
            "tool": tool,
            "returnCode": completed.returncode,
            "stdout": compact(completed.stdout, MAX_HELP_OUTPUT),
            "stderr": compact(completed.stderr, MAX_HELP_OUTPUT),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "status": "timeout",
            "tool": tool,
            "error": "help_probe_timeout",
            "stdout": compact(exc.stdout, MAX_HELP_OUTPUT),
            "stderr": compact(exc.stderr, MAX_HELP_OUTPUT),
        }


def process_snapshot():
    result = []
    for pid, process in list(BACKGROUND_PROCESSES.items()):
        code = process.poll()
        result.append(
            {
                "pid": pid,
                "running": code is None,
                "returnCode": code,
            }
        )
        if code is not None:
            BACKGROUND_PROCESSES.pop(pid, None)
    return result


def stop_process(pid):
    process = BACKGROUND_PROCESSES.get(int(pid))
    if not process:
        try:
            os.kill(int(pid), signal.SIGTERM)
            return {"status": "stopped", "pid": int(pid), "tracked": False}
        except ProcessLookupError:
            return {"status": "not_found", "pid": int(pid), "tracked": False}

    if os.name != "nt":
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
    else:
        process.terminate()

    BACKGROUND_PROCESSES.pop(process.pid, None)
    return {"status": "stopped", "pid": process.pid, "tracked": True}


def inventory():
    tools = discover_tools()
    by_kind = {}
    for tool in tools:
        by_kind[tool["kind"]] = by_kind.get(tool["kind"], 0) + 1
    return {
        "status": "ok",
        "engine": "O3DE",
        "engineRoot": str(ENGINE_ROOT),
        "o3deScript": str(O3DE_SCRIPT),
        "buildRoot": str(BUILD_ROOT),
        "toolCount": len(tools),
        "byKind": by_kind,
        "authRequiredForExecution": bool(BRIDGE_TOKEN),
        "scanRoots": [str(x.relative_to(ENGINE_ROOT)) if x != ENGINE_ROOT else "." for x in candidate_roots()],
    }


def self_test():
    if "o3de-cli:get-global-project" not in tool_index() and O3DE_SCRIPT.is_file():
        raise AssertionError("O3DE CLI registration discovery failed")
    test_root = WORKSPACE_ROOT
    if not is_relative_to(test_root, WORKSPACE_ROOT):
        raise AssertionError("workspace containment failed")
    validate_args(["--ok", "value"])
    try:
        validate_args(["\x00"])
    except ValueError:
        pass
    else:
        raise AssertionError("NUL validation failed")
    print(json.dumps({"status": "ok", **inventory()}, indent=2))


class Handler(BaseHTTPRequestHandler):
    server_version = "HyoukaO3DEBridge/2.0"

    def send_json(self, status, payload):
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header(
            "Access-Control-Allow-Headers", "Content-Type, Authorization"
        )
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Cache-Control", "no-store")
        if BRIDGE_TOKEN:
            self.send_header("WWW-Authenticate", "Bearer")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.end_headers()

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length > 200000:
            raise ValueError("Request body is too large")
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8"))

    def do_GET(self):
        path = urlparse(self.path).path
        try:
            if path == "/health":
                self.send_json(
                    200,
                    {
                        "status": "ok",
                        **inventory(),
                        "commands": sorted(TOP_LEVEL_COMMANDS),
                        "pid": os.getpid(),
                    },
                )
                return

            if path == "/discover":
                if reject_if_unauthorized(self):
                    return
                self.send_json(200, inventory() | {"tools": discover_tools()})
                return

            if path == "/processes":
                if reject_if_unauthorized(self):
                    return
                self.send_json(200, {"status": "ok", "processes": process_snapshot()})
                return

            self.send_json(404, {"status": "error", "error": "not_found"})
        except Exception as exc:
            self.send_json(
                500,
                {
                    "status": "error",
                    "error": type(exc).__name__,
                    "message": str(exc),
                },
            )

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            if path not in {"/help", "/cli"} and reject_if_unauthorized(self):
                return

            payload = self.read_json()

            if path == "/help":
                if not O3DE_SCRIPT.is_file():
                    raise RuntimeError(f"O3DE CLI not found at {O3DE_SCRIPT}")
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
                    shell=False,
                    check=False,
                )
                self.send_json(
                    200,
                    {
                        "status": "ok" if result.returncode == 0 else "failed",
                        "returnCode": result.returncode,
                        "stdout": compact(result.stdout, MAX_HELP_OUTPUT),
                        "stderr": compact(result.stderr, MAX_HELP_OUTPUT),
                    },
                )
                return

            if path == "/cli":
                command = str(payload.get("command", "")).strip()
                result = run_tool(
                    f"o3de-cli:{command}",
                    payload.get("args", []),
                    payload.get("cwd"),
                    payload.get("timeoutSeconds", 120),
                    bool(payload.get("background", False)),
                )
                self.send_json(200 if result["status"] in {"ok", "started"} else 400, result)
                return

            if path == "/invoke":
                result = run_tool(
                    str(payload.get("toolId", "")).strip(),
                    payload.get("args", []),
                    payload.get("cwd"),
                    payload.get("timeoutSeconds", 120),
                    bool(payload.get("background", False)),
                )
                self.send_json(200 if result["status"] in {"ok", "started"} else 400, result)
                return

            if path == "/probe":
                self.send_json(200, probe_tool(str(payload.get("toolId", "")).strip()))
                return

            if path == "/stop":
                self.send_json(200, stop_process(int(payload.get("pid"))))
                return

            if path == "/build":
                target = str(payload.get("target", "")).strip()
                if not target:
                    raise ValueError("target is required")
                if not BUILD_ROOT.is_dir():
                    raise RuntimeError(f"O3DE_BUILD_DIR does not exist: {BUILD_ROOT}")
                args = ["--target", target]
                jobs = int(payload.get("jobs", 0) or 0)
                config = str(payload.get("config", "")).strip()
                command = ["cmake", "--build", str(BUILD_ROOT)]
                if config:
                    command += ["--config", config]
                command += args
                if jobs > 0:
                    command += ["-j", str(min(jobs, 32))]
                result = run_tool(
                    f"cmake:{relative_path(ENGINE_ROOT / "CMakeLists.txt")}:{slugify(target)}",
                    [],
                    payload.get("cwd"),
                    payload.get("timeoutSeconds", 120),
                    bool(payload.get("background", False)),
                ) if False else subprocess_run_build(command, payload)
                self.send_json(200 if result["status"] in {"ok", "started"} else 400, result)
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
                {
                    "status": "error",
                    "error": type(exc).__name__,
                    "message": str(exc),
                },
            )

    def log_message(self, format_string, *args):
        return


def subprocess_run_build(command, payload):
    workdir = safe_workspace_path(payload.get("cwd"))
    timeout_seconds = max(1, min(int(payload.get("timeoutSeconds", 120) or 120), 600))
    environment = os.environ.copy()
    environment["O3DE_ROOT"] = str(ENGINE_ROOT)
    environment["O3DE_WORKSPACE_ROOT"] = str(WORKSPACE_ROOT)
    environment["O3DE_BUILD_DIR"] = str(BUILD_ROOT)

    if bool(payload.get("background", False)):
        process = subprocess.Popen(
            command,
            cwd=str(workdir),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=False,
            start_new_session=(os.name != "nt"),
            env=environment,
        )
        BACKGROUND_PROCESSES[process.pid] = process
        return {"status": "started", "pid": process.pid, "command": command}

    completed = subprocess.run(
        command,
        cwd=str(workdir),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        shell=False,
        timeout=timeout_seconds,
        check=False,
        env=environment,
    )
    return {
        "status": "ok" if completed.returncode == 0 else "failed",
        "command": command,
        "returnCode": completed.returncode,
        "stdout": compact(completed.stdout),
        "stderr": compact(completed.stderr),
    }


def main():
    parser = argparse.ArgumentParser(description="O3DE universal HTTP tool bridge")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
