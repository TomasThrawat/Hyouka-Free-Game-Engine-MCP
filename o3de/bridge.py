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

TOP_LEVEL_FALLBACKS = {
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
    "Downloads",
    ".vs",
}

MAX_DISCOVERED_TOOLS = 2000
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


def engine_relative(path):
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


def safe_workspace_path(value):
    if not value:
        return WORKSPACE_ROOT
    candidate = Path(value).expanduser().resolve()
    if not is_relative_to(candidate, WORKSPACE_ROOT):
        raise ValueError("cwd must stay inside O3DE_WORKSPACE_ROOT")
    if not candidate.is_dir():
        raise ValueError("cwd does not exist")
    return candidate


def candidate_roots():
    roots = []
    for name in SCAN_ROOT_NAMES:
        candidate = ENGINE_ROOT / name
        if candidate.is_dir() and candidate not in roots:
            roots.append(candidate)
    return roots


def read_text(path):
    return path.read_text(encoding="utf-8", errors="ignore")


def python_is_callable(path):
    try:
        text = read_text(path)
    except OSError:
        return False
    return (
        "__main__" in text
        or "argparse" in text
        or re.search(r"(^|\n)\s*def\s+main\s*\(", text) is not None
        or re.search(r"(^|\n)\s*click\.command", text) is not None
        or re.search(r"(^|\n)\s*@app\.command", text) is not None
    )


def executable_file(path):
    try:
        mode = path.stat().st_mode
    except OSError:
        return False
    return bool(mode & stat.S_IXUSR) and path.is_file()


def parse_cmake(path):
    try:
        text = read_text(path)
    except OSError:
        return [], []

    targets = []
    tests = []

    target_pattern = re.compile(
        r"\b(add_executable|add_custom_target)\s*\(\s*([A-Za-z0-9_.:+-]+)",
        re.IGNORECASE,
    )
    for match in target_pattern.finditer(text):
        targets.append((match.group(1).lower(), match.group(2)))

    test_pattern = re.compile(
        r"\badd_test\s*\(\s*NAME\s+([A-Za-z0-9_.:+-]+)",
        re.IGNORECASE,
    )
    for match in test_pattern.finditer(text):
        tests.append(match.group(1))

    return targets, tests


def discover_top_level_commands():
    commands = set(TOP_LEVEL_FALLBACKS)
    if not O3DE_SCRIPT.is_file():
        return sorted(commands)
    try:
        text = read_text(O3DE_SCRIPT)
    except OSError:
        return sorted(commands)

    for match in re.finditer(
        r"\badd_parser\s*\(\s*[\"']([^\"']+)[\"']",
        text,
    ):
        commands.add(match.group(1))

    return sorted(commands)


def add_tool(tools, tool):
    if len(tools) >= MAX_DISCOVERED_TOOLS:
        return
    tools.setdefault(tool["id"], tool)


def discover_tools():
    tools = {}
    visited = set()

    for root in candidate_roots():
        for current, dirs, files in os.walk(root):
            current_path = Path(current).resolve()
            if current_path in visited or excluded(current_path):
                dirs[:] = []
                continue
            visited.add(current_path)

            dirs[:] = [
                directory
                for directory in dirs
                if directory not in EXCLUDED_PARTS
                and not directory.startswith(".")
            ]

            for filename in files:
                path = (current_path / filename).resolve()
                if excluded(path) or not path.is_file():
                    continue
                if not is_relative_to(path, ENGINE_ROOT):
                    continue

                rel = engine_relative(path)
                lower = filename.lower()

                if lower.endswith(".py") and python_is_callable(path):
                    add_tool(
                        tools,
                        {
                            "id": f"py:{slugify(rel)}",
                            "kind": "python",
                            "name": path.stem,
                            "path": rel,
                            "call": [sys.executable, str(path)],
                            "callable": True,
                            "source": "O3DE Python/script tree",
                        },
                    )
                    continue

                if lower.endswith(".sh") and (
                    "/scripts/" in f"/{rel.lower()}"
                    or "/tools/" in f"/{rel.lower()}"
                    or "/code/tools/" in f"/{rel.lower()}"
                ):
                    add_tool(
                        tools,
                        {
                            "id": f"sh:{slugify(rel)}",
                            "kind": "shell-script",
                            "name": path.stem,
                            "path": rel,
                            "call": ["bash", str(path)],
                            "callable": True,
                            "source": "O3DE script/tool tree",
                        },
                    )
                    continue

                if os.name == "nt" and lower.endswith((".exe", ".cmd", ".bat")):
                    add_tool(
                        tools,
                        {
                            "id": f"exe:{slugify(rel)}",
                            "kind": "executable",
                            "name": path.stem,
                            "path": rel,
                            "call": [str(path)],
                            "callable": True,
                            "source": "O3DE built tool tree",
                        },
                    )
                    continue

                if os.name != "nt" and executable_file(path):
                    add_tool(
                        tools,
                        {
                            "id": f"exe:{slugify(rel)}",
                            "kind": "executable",
                            "name": path.stem,
                            "path": rel,
                            "call": [str(path)],
                            "callable": True,
                            "source": "O3DE built tool tree",
                        },
                    )
                    continue

                if lower == "cmakelists.txt":
                    targets, tests = parse_cmake(path)
                    for target_kind, target in targets:
                        add_tool(
                            tools,
                            {
                                "id": f"cmake:{slugify(rel)}:{slugify(target)}",
                                "kind": "cmake-target",
                                "name": target,
                                "path": rel,
                                "target": target,
                                "targetKind": target_kind,
                                "callable": True,
                                "source": "O3DE CMake tool target",
                            },
                        )
                    for test_name in tests:
                        add_tool(
                            tools,
                            {
                                "id": f"ctest:{slugify(rel)}:{slugify(test_name)}",
                                "kind": "ctest",
                                "name": test_name,
                                "path": rel,
                                "testName": test_name,
                                "callable": True,
                                "source": "O3DE CTest registration",
                            },
                        )

    if O3DE_SCRIPT.is_file() and is_relative_to(O3DE_SCRIPT, ENGINE_ROOT):
        for command in discover_top_level_commands():
            add_tool(
                tools,
                {
                    "id": f"o3de-cli:{command}",
                    "kind": "o3de-cli",
                    "name": command,
                    "path": engine_relative(O3DE_SCRIPT),
                    "call": [sys.executable, str(O3DE_SCRIPT), command],
                    "callable": True,
                    "source": "O3DE scripts/o3de.py top-level CLI",
                },
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
    kind = tool["kind"]
    if kind in {"python", "shell-script", "executable", "o3de-cli"}:
        return tool["call"] + args

    if kind == "cmake-target":
        if not BUILD_ROOT.is_dir():
            raise RuntimeError(
                f"O3DE build directory not found at {BUILD_ROOT}. "
                "Set O3DE_BUILD_DIR to a configured CMake build tree."
            )
        return ["cmake", "--build", str(BUILD_ROOT), "--target", tool["target"], *args]

    if kind == "ctest":
        if not BUILD_ROOT.is_dir():
            raise RuntimeError(
                f"O3DE build directory not found at {BUILD_ROOT}. "
                "Set O3DE_BUILD_DIR to a configured CTest build tree."
            )
        return [
            "ctest",
            "--test-dir",
            str(BUILD_ROOT),
            "--output-on-failure",
            "-R",
            f"^{re.escape(tool['testName'])}$",
            *args,
        ]

    raise ValueError(f"Unsupported tool kind: {kind}")


def execution_environment():
    env = os.environ.copy()
    env["O3DE_ROOT"] = str(ENGINE_ROOT)
    env["O3DE_WORKSPACE_ROOT"] = str(WORKSPACE_ROOT)
    env["O3DE_BUILD_DIR"] = str(BUILD_ROOT)
    return env


def run_tool(tool_id, args, cwd, timeout_seconds, background=False):
    index = tool_index()
    tool = index.get(tool_id)
    if not tool:
        raise ValueError(
            "Unknown tool_id. Call /discover first and use an id from the returned inventory."
        )

    clean_args = validate_args(args)
    workdir = safe_workspace_path(cwd)
    timeout_seconds = max(1, min(int(timeout_seconds or 120), 600))
    command = command_for_tool(tool, clean_args)
    env = execution_environment()

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
            env=env,
        )
        BACKGROUND_PROCESSES[process.pid] = process
        return {
            "status": "started",
            "toolId": tool_id,
            "kind": tool["kind"],
            "path": tool["path"],
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
        env=env,
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
    if tool["kind"] in {"cmake-target", "ctest"}:
        raise ValueError("Build/test entries are not --help probeable")

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
            env=execution_environment(),
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
        result.append({"pid": pid, "running": code is None, "returnCode": code})
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


def filter_tools(query="", kind="", callable_only=True):
    items = discover_tools()
    query = str(query or "").strip().lower()
    kind = str(kind or "").strip().lower()
    result = []
    for tool in items:
        if callable_only and not tool.get("callable"):
            continue
        haystack = " ".join(
            [
                str(tool.get("id", "")),
                str(tool.get("name", "")),
                str(tool.get("path", "")),
                str(tool.get("kind", "")),
                str(tool.get("source", "")),
            ]
        ).lower()
        if query and query not in haystack:
            continue
        if kind and tool.get("kind", "").lower() != kind:
            continue
        result.append(tool)
    return result


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
        "topLevelCommandCount": len(discover_top_level_commands()),
        "authRequiredForExecution": bool(BRIDGE_TOKEN),
        "scanRoots": [str(x.relative_to(ENGINE_ROOT)) for x in candidate_roots()],
    }


def self_test():
    index = tool_index()
    bridge_id = f"py:{slugify(engine_relative(Path(__file__)))}"
    if bridge_id not in index:
        raise AssertionError("bridge discovery failed")

    validate_args(["--ok", "value"])
    try:
        validate_args(["\x00"])
    except ValueError:
        pass
    else:
        raise AssertionError("NUL validation failed")

    cmake_text = """
    add_executable(TestTool main.cpp)
    add_custom_target(CustomTool)
    add_test(NAME SmokeTest COMMAND TestTool)
    """
    tmp = WORKSPACE_ROOT / ".o3de-mcp-self-test.cmake"
    try:
        tmp.write_text(cmake_text, encoding="utf-8")
        targets, tests = parse_cmake(tmp)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass

    if ("add_executable", "TestTool") not in targets:
        raise AssertionError("CMake executable parsing failed")
    if "SmokeTest" not in tests:
        raise AssertionError("CTest parsing failed")

    direct = command_for_tool(
        {"kind": "o3de-cli", "call": [sys.executable, "/tmp/o3de.py"]},
        [],
    )
    if direct[:2] != [sys.executable, "/tmp/o3de.py"]:
        raise AssertionError("command building failed")

    print(json.dumps({"status": "ok", **inventory()}, indent=2))


class Handler(BaseHTTPRequestHandler):
    server_version = "HyoukaO3DEBridge/3.0"

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
                        **inventory(),
                        "commands": discover_top_level_commands(),
                        "pid": os.getpid(),
                    },
                )
                return

            if path == "/discover":
                if reject_if_unauthorized(self):
                    return
                self.send_json(200, {**inventory(), "tools": discover_tools()})
                return

            if path == "/find":
                if reject_if_unauthorized(self):
                    return
                query = urlparse(self.path).query
                params = {}
                for pair in query.split("&"):
                    if "=" in pair:
                        key, value = pair.split("=", 1)
                        params[key] = value
                found = filter_tools(
                    params.get("q", ""),
                    params.get("kind", ""),
                    params.get("callable", "true").lower() != "false",
                )
                self.send_json(
                    200,
                    {
                        **inventory(),
                        "tools": found,
                        "returnedTools": len(found),
                    },
                )
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
            if path not in {"/help"} and reject_if_unauthorized(self):
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
                    env=execution_environment(),
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
                self.send_json(
                    200 if result["status"] in {"ok", "started"} else 400,
                    result,
                )
                return

            if path == "/invoke":
                result = run_tool(
                    str(payload.get("toolId", "")).strip(),
                    payload.get("args", []),
                    payload.get("cwd"),
                    payload.get("timeoutSeconds", 120),
                    bool(payload.get("background", False)),
                )
                self.send_json(
                    200 if result["status"] in {"ok", "started"} else 400,
                    result,
                )
                return

            if path == "/probe":
                self.send_json(
                    200,
                    probe_tool(str(payload.get("toolId", "")).strip()),
                )
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

                command = ["cmake", "--build", str(BUILD_ROOT)]
                config = str(payload.get("config", "")).strip()
                if config:
                    command += ["--config", config]
                command += ["--target", target]

                jobs = int(payload.get("jobs", 0) or 0)
                if jobs > 0:
                    command += ["-j", str(min(jobs, 32))]

                result = run_build(command, payload)
                self.send_json(
                    200 if result["status"] in {"ok", "started"} else 400,
                    result,
                )
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


def run_build(command, payload):
    workdir = safe_workspace_path(payload.get("cwd"))
    timeout_seconds = max(
        1, min(int(payload.get("timeoutSeconds", 120) or 120), 600)
    )
    env = execution_environment()

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
            env=env,
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
        env=env,
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
