import json
import mimetypes
import os
import re
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

import bpy


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "blender_output"
OUTPUT.mkdir(parents=True, exist_ok=True)
HOST = os.environ.get("BLENDER_BRIDGE_HOST", "0.0.0.0")
PORT = int(os.environ.get("BLENDER_BRIDGE_PORT", "9765"))


def clean_name(value: str, fallback: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", value or "").strip("._")
    return value[:120] or fallback


def vector3(value, default=(0.0, 0.0, 0.0)):
    if value is None:
        return default
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError("Expected an array of exactly 3 numbers")
    return tuple(float(x) for x in value)


def color4(value, default=(0.35, 0.55, 0.95, 1.0)):
    if value is None:
        return default
    if not isinstance(value, (list, tuple)) or len(value) not in (3, 4):
        raise ValueError("Expected RGB or RGBA color")
    parts = tuple(float(x) for x in value)
    if len(parts) == 3:
        parts = parts + (1.0,)
    return tuple(max(0.0, min(1.0, x)) for x in parts)


def material_for(name: str, color):
    material = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    material.diffuse_color = color
    return material


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablocks in (
        bpy.data.meshes,
        bpy.data.curves,
        bpy.data.materials,
        bpy.data.cameras,
        bpy.data.lights,
    ):
        for block in list(datablocks):
            if block.users == 0:
                datablocks.remove(block)


def add_primitive(data):
    primitive = str(data.get("primitive", "cube")).lower()
    name = clean_name(data.get("name"), f"{primitive}_1")
    location = vector3(data.get("location"))
    rotation = vector3(data.get("rotation"))
    scale = vector3(data.get("scale"), (1.0, 1.0, 1.0))
    color = color4(data.get("color"))

    ops = {
        "cube": lambda: bpy.ops.mesh.primitive_cube_add(),
        "sphere": lambda: bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=16),
        "cylinder": lambda: bpy.ops.mesh.primitive_cylinder_add(vertices=32),
        "cone": lambda: bpy.ops.mesh.primitive_cone_add(vertices=32),
        "torus": lambda: bpy.ops.mesh.primitive_torus_add(major_segments=32, minor_segments=12),
        "plane": lambda: bpy.ops.mesh.primitive_plane_add(size=2.0),
    }

    if primitive not in ops:
        raise ValueError(f"Unsupported primitive: {primitive}")

    ops[primitive]()
    obj = bpy.context.object
    obj.name = name
    obj.location = location
    obj.rotation_euler = rotation
    obj.scale = scale

    material = material_for(f"{name}_Material", color)
    obj.data.materials.append(material)

    return object_info(obj)


def object_info(obj):
    return {
        "name": obj.name,
        "type": obj.type,
        "location": [round(float(x), 5) for x in obj.location],
        "rotation": [round(float(x), 5) for x in obj.rotation_euler],
        "scale": [round(float(x), 5) for x in obj.scale],
    }


def ensure_camera():
    camera = bpy.data.objects.get("HyoukaCamera")
    if camera is None or camera.type != "CAMERA":
        bpy.ops.object.camera_add(location=(7.0, -7.0, 5.0))
        camera = bpy.context.object
        camera.name = "HyoukaCamera"
    camera.location = (7.0, -7.0, 5.0)
    target = bpy.data.objects.get("HyoukaCameraTarget")
    if target is None:
        bpy.ops.object.empty_add(location=(0.0, 0.0, 0.5))
        target = bpy.context.object
        target.name = "HyoukaCameraTarget"
    direction = target.location - camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = camera
    return camera


def ensure_light():
    light = bpy.data.objects.get("HyoukaKeyLight")
    if light is None or light.type != "LIGHT":
        bpy.ops.object.light_add(type="AREA", location=(4.0, -3.0, 6.0))
        light = bpy.context.object
        light.name = "HyoukaKeyLight"
    light.data.energy = 900
    light.data.shape = "DISK"
    light.data.size = 5
    target = bpy.data.objects.get("HyoukaCameraTarget")
    if target:
        direction = target.location - light.location
        light.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    return light


def basic_scene():
    clear_scene()
    add_primitive({
        "primitive": "plane",
        "name": "Ground",
        "scale": [7.0, 7.0, 7.0],
        "color": [0.08, 0.10, 0.12, 1.0],
    })
    add_primitive({
        "primitive": "cube",
        "name": "Player",
        "location": [0.0, 0.0, 0.75],
        "scale": [0.8, 1.2, 0.75],
        "color": [0.05, 0.45, 1.0, 1.0],
    })
    add_primitive({
        "primitive": "cube",
        "name": "Obstacle_A",
        "location": [2.5, 1.2, 0.5],
        "scale": [0.6, 0.6, 0.5],
        "color": [1.0, 0.25, 0.08, 1.0],
    })
    add_primitive({
        "primitive": "sphere",
        "name": "Pickup",
        "location": [-2.0, -1.0, 0.8],
        "scale": [0.45, 0.45, 0.45],
        "color": [1.0, 0.85, 0.1, 1.0],
    })
    ensure_camera()
    ensure_light()
    world = bpy.context.scene.world or bpy.data.worlds.new("HyoukaWorld")
    bpy.context.scene.world = world
    world.color = (0.025, 0.03, 0.05)
    return {"objects": [object_info(o) for o in bpy.context.scene.objects]}


def safe_output_path(filename: str, default_name: str) -> Path:
    filename = clean_name(filename, default_name)
    if not Path(filename).suffix:
        filename += Path(default_name).suffix
    target = (OUTPUT / filename).resolve()
    if OUTPUT not in target.parents:
        raise ValueError("Artifact path must stay inside blender_output")
    return target


def render_scene(data):
    camera = ensure_camera()
    ensure_light()
    width = int(data.get("width", 640))
    height = int(data.get("height", 360))
    width = max(320, min(1280, width))
    height = max(180, min(720, height))
    filename = clean_name(data.get("filename"), "render.png")
    if not filename.lower().endswith(".png"):
        filename += ".png"
    target = safe_output_path(filename, "render.png")
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    scene.render.filepath = str(target)
    scene.render.image_settings.file_format = "PNG"
    scene.camera = camera
    bpy.ops.render.render(write_still=True)
    return {"filename": filename, "path": str(target), "size": [width, height]}


class Handler(BaseHTTPRequestHandler):
    server_version = "HyoukaBlenderBridge/1.0"

    def json_response(self, status, payload):
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.end_headers()

    def do_GET(self):
        url = urlparse(self.path)
        try:
            if url.path == "/health":
                self.json_response(200, {
                    "status": "ok",
                    "engine": "Blender",
                    "version": bpy.app.version_string,
                    "port": PORT,
                })
                return
            if url.path == "/scene/objects":
                self.json_response(200, {
                    "objects": [object_info(o) for o in bpy.context.scene.objects]
                })
                return
            if url.path.startswith("/files/"):
                rel = unquote(url.path[len("/files/"):])
                target = (OUTPUT / rel).resolve()
                if OUTPUT not in target.parents or not target.is_file():
                    self.json_response(404, {"error": "artifact_not_found"})
                    return
                body = target.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "public, max-age=31536000, immutable")
                self.end_headers()
                self.wfile.write(body)
                return
            self.json_response(404, {"error": "not_found"})
        except Exception as exc:
            self.json_response(500, {"error": type(exc).__name__, "message": str(exc)})

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length else b"{}"
            data = json.loads(raw.decode("utf-8"))
            if self.path == "/scene/new":
                clear_scene()
                self.json_response(200, {"status": "ok", "message": "scene_cleared"})
                return
            if self.path == "/scene/basic":
                self.json_response(200, {"status": "ok", **basic_scene()})
                return
            if self.path == "/object/add":
                self.json_response(200, {"status": "ok", "object": add_primitive(data)})
                return
            if self.path == "/object/transform":
                name = str(data.get("name", ""))
                obj = bpy.data.objects.get(name)
                if obj is None:
                    raise ValueError(f"Object not found: {name}")
                if "location" in data:
                    obj.location = vector3(data["location"])
                if "rotation" in data:
                    obj.rotation_euler = vector3(data["rotation"])
                if "scale" in data:
                    obj.scale = vector3(data["scale"], (1.0, 1.0, 1.0))
                self.json_response(200, {"status": "ok", "object": object_info(obj)})
                return
            if self.path == "/object/delete":
                name = str(data.get("name", ""))
                obj = bpy.data.objects.get(name)
                if obj is None:
                    raise ValueError(f"Object not found: {name}")
                bpy.data.objects.remove(obj, do_unlink=True)
                self.json_response(200, {"status": "ok", "deleted": name})
                return
            if self.path == "/scene/save":
                target = safe_output_path(data.get("filename"), "scene.blend")
                bpy.ops.wm.save_as_mainfile(filepath=str(target))
                self.json_response(200, {"status": "ok", "filename": target.name, "path": str(target)})
                return
            if self.path == "/scene/render":
                self.json_response(200, {"status": "ok", **render_scene(data)})
                return
            if self.path == "/scene/export-glb":
                target = safe_output_path(data.get("filename"), "scene.glb")
                bpy.ops.export_scene.gltf(filepath=str(target), export_format="GLB", use_selection=False)
                self.json_response(200, {"status": "ok", "filename": target.name, "path": str(target)})
                return
            self.json_response(404, {"error": "not_found"})
        except Exception as exc:
            self.json_response(400, {"error": type(exc).__name__, "message": str(exc)})

    def log_message(self, fmt, *args):
        print("[blender-bridge] " + fmt % args, flush=True)


print(f"Starting Blender bridge on {HOST}:{PORT}", flush=True)
HTTPServer((HOST, PORT), Handler).serve_forever()
