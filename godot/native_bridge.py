#!/usr/bin/env python3
import base64
import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse, urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import public_bridge as bridge

NATIVE_PROCS = {}
LOG_HANDLES = {}
_NATIVE_LAUNCH = False

def session_file(project_dir):
    return Path(project_dir) / ".godot-mcp-native" / "session.json"

def save_session(project_dir, pid, port):
    p = session_file(project_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"pid": int(pid), "port": int(port), "project": str(project_dir), "stdoutLog": str(Path(project_dir)/".godot-mcp-native"/"stdout.log"), "stderrLog": str(Path(project_dir)/".godot-mcp-native"/"stderr.log")}), encoding="utf-8")

def load_session(pid=None, project_dir=None):
    candidates = []
    if project_dir:
        candidates.append(session_file(project_dir))
    root = Path(bridge.ROOT) / "projects" if "bridge" in globals() else None
    if root and root.is_dir():
        candidates.extend(root.glob("*/.godot-mcp-native/session.json"))
    for path in candidates:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if pid is not None and int(data.get("pid", -1)) != int(pid):
                continue
            project = Path(str(data["project"]))
            if not project.is_dir():
                continue
            return data
        except Exception:
            continue
    return None

def clear_session(project_dir):
    try:
        session_file(project_dir).unlink(missing_ok=True)
    except Exception:
        pass

def pid_alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False

def read_logs(session):
    stdout = ""
    stderr = ""
    try:
        path = Path(str(session.get("stdoutLog", "")))
        if path.is_file():
            stdout = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        pass
    try:
        path = Path(str(session.get("stderrLog", "")))
        if path.is_file():
            stderr = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        pass
    return stdout, stderr
ORIGINAL_RUN = bridge.run
ORIGINAL_INVOKE = bridge.invoke
ORIGINAL_TOOLS = bridge.tools

def free_port():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]
    finally:
        sock.close()

def cleanup_native(project_dir):
    project = Path(project_dir)
    native_dir = project / ".godot-mcp-native"
    backup = native_dir / "project.godot.original"
    project_file = project / "project.godot"
    try:
        if backup.is_file():
            project_file.write_text(backup.read_text(encoding="utf-8"), encoding="utf-8")
    except Exception:
        pass
    if native_dir.exists():
        shutil.rmtree(native_dir, ignore_errors=True)

def install_native(project_dir, port):
    project = Path(project_dir)
    project_file = project / "project.godot"
    helper_source = HERE / "native_game_view.gd"
    if not project_file.is_file():
        raise ValueError("Godot project.godot not found")
    if not helper_source.is_file():
        raise ValueError("native_game_view.gd is missing")
    cleanup_native(project)
    native_dir = project / ".godot-mcp-native"
    native_dir.mkdir(parents=True, exist_ok=True)
    original = project_file.read_text(encoding="utf-8")
    (native_dir / "project.godot.original").write_text(original, encoding="utf-8")
    helper_text = helper_source.read_text(encoding="utf-8")
    helper_text = helper_text.replace("var listening_port := 0", "var listening_port := " + str(int(port)))
    (native_dir / "game_view.gd").write_text(helper_text, encoding="utf-8")
    line = 'GodotMcpNativeGameView="*res://.godot-mcp-native/game_view.gd"'
    start = original.find("[autoload]")
    if start < 0:
        patched = original.rstrip() + "\n\n[autoload]\n" + line + "\n"
    else:
        end = original.find("\n[", start + 1)
        if end < 0:
            end = len(original)
        section = original[start:end]
        if "GodotMcpNativeGameView=" in section:
            patched = original
        else:
            pos = start + len("[autoload]")
            patched = original[:pos] + "\n" + line + original[pos:]
    project_file.write_text(patched, encoding="utf-8")
    return port

def native_run(args, cwd=None, timeout=120, bg=False):
    if not bg:
        return ORIGINAL_RUN(args, cwd, timeout, bg)
    wd = bridge.inside(cwd)
    if not (wd / "project.godot").is_file():
        return ORIGINAL_RUN(args, cwd, timeout, bg)
    port = free_port()
    install_native(wd, port)
    normalized = bridge.normalize(args)
    cmd = [str(bridge.GODOT)] + normalized
    env = os.environ.copy()
    native_dir = wd / ".godot-mcp-native"
    native_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = native_dir / "stdout.log"
    stderr_path = native_dir / "stderr.log"
    stdout_handle = open(stdout_path, "a", encoding="utf-8")
    stderr_handle = open(stderr_path, "a", encoding="utf-8")
    p = subprocess.Popen(
        cmd,
        cwd=wd,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=stdout_handle,
        stderr=stderr_handle,
        text=True,
        shell=False,
        start_new_session=True,
    )
    LOG_HANDLES[p.pid] = (stdout_handle, stderr_handle)
    bridge.PROCS[p.pid] = (p, __import__("time").time(), cmd, str(wd))
    NATIVE_PROCS[p.pid] = {"port": port, "project": str(wd)}
    save_session(wd, p.pid, port)
    return {"status":"started","pid":p.pid,"command":cmd,"cwd":str(wd),"nativeGodotControl":True,"port":port}

def native_start_project(args, cwd=None, timeout=120):
    args = list(args)
    repo_url = None
    repo_ref = "main"
    clean = []
    index = 0
    while index < len(args):
        value = args[index]
        if value == "--repo-url":
            if index + 1 >= len(args):
                raise ValueError("--repo-url requires a value")
            repo_url = args[index + 1]
            index += 2
        elif value == "--repo-ref":
            if index + 1 >= len(args):
                raise ValueError("--repo-ref requires a value")
            repo_ref = args[index + 1]
            index += 2
        else:
            clean.append(value)
            index += 1

    if repo_url:
        project_dir = bridge.sync_github_repo(repo_url, repo_ref)
        imported = ORIGINAL_RUN(
            ["--headless", "--editor", "--import", "--quit"],
            cwd=str(project_dir),
            timeout=180,
            bg=False,
        )
        if imported.get("status") != "ok":
            raise ValueError("Godot import failed: " + str(imported.get("stderr", ""))[-4000:])
        cwd = str(project_dir)
    else:
        project_dir = bridge.inside(cwd)
        cwd = str(project_dir)

    if "--path" not in clean and "-p" not in clean:
        clean = ["--path", str(project_dir)] + clean

    return native_run(clean, cwd, timeout, True)

def native_invoke(tool_id, args, cwd=None, timeout=120, bg=False):
    if tool_id == "godot-run-project" and bg:
        return native_start_project(args, cwd, timeout)
    if tool_id not in {"godot-game-status","godot-game-view","godot-game-input"}:
        return ORIGINAL_INVOKE(tool_id, args, cwd, timeout, bg)
    if not args or not str(args[0]).isdigit():
        raise ValueError("first arg must be the Godot game PID")
    pid = int(args[0])
    proc = bridge.PROCS.get(pid)
    info = NATIVE_PROCS.get(pid)
    session = None
    if not info:
        session = load_session(pid=pid)
        if session:
            info = {"port": int(session["port"]), "project": str(session["project"])}
            NATIVE_PROCS[pid] = info
    if not info:
        raise ValueError("PID is not a running Godot project with native control")
    alive = proc is not None and proc[0].poll() is None
    if proc is None:
        alive = pid_alive(pid)
    if not alive:
        session_data = load_session(pid=pid) or {"pid":pid}
        stdout, stderr = read_logs(session_data)
        return {
            "status":"stopped",
            "engine":"Godot",
            "pid":pid,
            "returnCode":proc[0].returncode if proc is not None else None,
            "stdout":stdout,
            "stderr":stderr,
            "message":"Godot game process is no longer running"
        }
    base = "http://127.0.0.1:" + str(info["port"])
    if tool_id == "godot-game-status":
        with urlopen(Request(base + "/state"), timeout=5) as response:
            result = json.loads(response.read())
        session_data = load_session(pid=pid) or {}
        stdout, stderr = read_logs(session_data)
        result.update({"pid": pid, "stdoutTail": stdout[-6000:], "stderrTail": stderr[-6000:]})
        return result
    if tool_id == "godot-game-view":
        try:
            with urlopen(Request(base + "/view"), timeout=30) as response:
                data = response.read()
                content_type = response.headers.get("Content-Type", "")
                if not content_type.startswith("image/png"):
                    return json.loads(data)
                return {
                "status":"ok",
                "engine":"Godot",
                "pid":pid,
                "width":int(response.headers.get("X-Godot-Viewport-Width","0")),
                "height":int(response.headers.get("X-Godot-Viewport-Height","0")),
                    "content":[{"type":"image","data":base64.b64encode(data).decode("ascii"),"mimeType":"image/png"}],
                }
        except HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            return {"status":"error","engine":"Godot","httpStatus":exc.code,"message":body}
        except URLError as exc:
            return {"status":"error","engine":"Godot","message":str(exc)}

    if len(args) < 2:
        raise ValueError("godot-game-input requires PID and a JSON event")
    event = json.loads(args[1])
    if not isinstance(event, dict):
        raise ValueError("input event must be a JSON object")
    query = urlencode({str(k): str(v).lower() if isinstance(v, bool) else str(v) for k,v in event.items()})
    with urlopen(Request(base + "/input?" + query), timeout=5) as response:
        return json.loads(response.read())

def native_tools():
    items = list(ORIGINAL_TOOLS())
    items.extend([
        {"id":"godot-game-status","kind":"godot","callable":True,"description":"Read live state directly from a running Godot game process. Arg 1 is the PID returned by godot-run-project."},
        {"id":"godot-game-view","kind":"godot","callable":True,"description":"Capture the current rendered Godot Viewport directly from the running game. The pixels come from Godot Viewport.get_texture().get_image(). No browser or external desktop capture."},
        {"id":"godot-game-input","kind":"godot","callable":True,"description":"Inject a real Godot InputEvent directly into the running game. Arg 1 is PID; arg 2 is a JSON event object for click, tap, motion, touch, key, or action input."},
    ])
    return items

class NativeHandler(bridge.H):
    def do_POST(self):
        try:
            path = urlparse(self.path).path
            body = self.body()
            if path == "/invoke":
                result = native_invoke(
                    str(body["toolId"]),
                    body.get("args", []),
                    body.get("cwd"),
                    body.get("timeoutSeconds", 120),
                    bool(body.get("background")),
                )
                return self.send(200, result)
            if path == "/stop":
                pid = int(body["pid"])
                item = bridge.PROCS.get(pid)
                info = NATIVE_PROCS.get(pid) or load_session(pid=pid)
                if not item and not info:
                    raise ValueError("unknown process")
                if item:
                    if item[0].poll() is None:
                        os.killpg(item[0].pid, bridge.signal.SIGTERM)
                elif pid_alive(pid):
                    os.killpg(pid, bridge.signal.SIGTERM)
                info = NATIVE_PROCS.pop(pid, None) or (info if isinstance(info, dict) else None)
                if info:
                    cleanup_native(info["project"])
                    clear_session(info["project"])
                handle_pair = LOG_HANDLES.pop(pid, None)
                if handle_pair:
                    for handle in handle_pair:
                        try:
                            handle.flush()
                            handle.close()
                        except Exception:
                            pass
                bridge.PROCS.pop(pid, None)
                return self.send(200, {"status":"stopped","pid":pid})
            return super().do_POST()
        except Exception as exc:
            return self.send(400, {"status":"error","message":str(exc)})

    def do_GET(self):
        if urlparse(self.path).path == "/selftest":
            check = bridge.ROOT / ".godot-mcp-native-check"
            if check.exists():
                shutil.rmtree(check, ignore_errors=True)
            (check / "native").mkdir(parents=True, exist_ok=True)
            (check / "project.godot").write_text(
                '[application]\nconfig/name="GodotMcpNativeCheck"\n[autoload]\nGodotMcpNativeGameView="*res://native/game_view.gd"\n',
                encoding="utf-8",
            )
            shutil.copy2(HERE / "native_game_view.gd", check / "native/game_view.gd")
            native_check = ORIGINAL_RUN(
                ["--headless","--path",str(check),"--editor","--quit"],
                cwd=str(check),
                timeout=60,
                bg=False,
            )
            shutil.rmtree(check, ignore_errors=True)
            smoke = ORIGINAL_RUN(
                ["--headless","--path",str(bridge.ROOT/"runtime/godot-smoke-test"),"--editor","--quit"],
                timeout=120,
                bg=False,
            )
            return self.send(200, {
                "status":"ok" if native_check["status"]=="ok" and smoke["status"]=="ok" else "failed",
                "nativeControlCheck":native_check,
                "smokeTest":smoke,
            })
        return super().do_GET()

bridge.run = native_run
bridge.invoke = native_invoke
bridge.tools = native_tools

if __name__ == "__main__":
    if not bridge.GODOT.is_file():
        raise SystemExit("Godot binary not found: " + str(bridge.GODOT))
    bridge.ThreadingHTTPServer((bridge.HOST, bridge.PORT), NativeHandler).serve_forever()
