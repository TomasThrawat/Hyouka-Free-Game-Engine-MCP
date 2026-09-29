extends Node

var server := TCPServer.new()
var clients: Array[StreamPeerTCP] = []
var listening_port: int = 0
var native_ready: bool = false

func _ready() -> void:
    if listening_port <= 0:
        push_error("Godot MCP native view server has no configured port")
        return
    var err: Error = server.listen(listening_port, "127.0.0.1")
    if err != OK:
        push_error("Godot MCP native view server failed: " + str(err))
        return
    native_ready = true
    print("GODOT_MCP_NATIVE_VIEW_READY port=" + str(listening_port))

func _process(_delta: float) -> void:
    while server.is_connection_available():
        var client: StreamPeerTCP = server.take_connection()
        if client == null:
            break
        client.set_no_delay(true)
        clients.append(client)
    for client in clients.duplicate():
        client.poll()
        if client.get_status() != StreamPeerSocket.STATUS_CONNECTED:
            clients.erase(client)
            continue
        var available: int = client.get_available_bytes()
        if available <= 0:
            continue
        var request: String = client.get_string(available)
        _handle_request(client, request)
        if clients.has(client):
            clients.erase(client)

func _handle_request(client: StreamPeerTCP, request: String) -> void:
    var header_end: int = request.find("\r\n\r\n")
    if header_end < 0:
        _send_json(client, 400, {"status":"error","message":"invalid HTTP request"})
        return
    var first_line: String = request.substr(0, header_end).split("\r\n")[0]
    var parts: PackedStringArray = first_line.split(" ")
    if parts.size() < 2 or parts[0] != "GET":
        _send_json(client, 400, {"status":"error","message":"GET required"})
        return
    var target_parts: PackedStringArray = parts[1].split("?", false, 1)
    var path: String = target_parts[0]
    var query: Dictionary = {}
    if target_parts.size() > 1:
        query = _parse_query(target_parts[1])
    match path:
        "/state":
            _send_json(client, 200, _state())
        "/view":
            _queue_view(client)
        "/input":
            _handle_input(client, query)
        _:
            _send_json(client, 404, {"status":"error","message":"not_found"})

func _parse_query(text: String) -> Dictionary:
    var result: Dictionary = {}
    for pair in text.split("&", false):
        var kv: PackedStringArray = pair.split("=", false, 1)
        var key: String = kv[0].uri_decode()
        result[key] = kv[1].uri_decode() if kv.size() > 1 else ""
    return result

func _queue_view(client: StreamPeerTCP) -> void:
    call_deferred("_finish_view", client)

func _finish_view(client: StreamPeerTCP) -> void:
    await get_tree().process_frame
    await RenderingServer.frame_post_draw
    await get_tree().process_frame
    if client == null or client.get_status() != StreamPeerSocket.STATUS_CONNECTED:
        return
    var texture: ViewportTexture = get_viewport().get_texture()
    if texture == null:
        _send_json(client, 500, {"status":"error","message":"viewport texture unavailable"})
        return
    var image: Image = texture.get_image()
    if image == null:
        _send_json(client, 500, {"status":"error","message":"viewport image unavailable"})
        return
    if image.get_width() <= 0 or image.get_height() <= 0:
        _send_json(client, 500, {"status":"error","message":"viewport image has invalid size"})
        return
    image.convert(Image.FORMAT_RGBA8)
    var png: PackedByteArray = image.save_png_to_buffer()
    if png.is_empty():
        _send_json(client, 500, {"status":"error","message":"PNG capture failed"})
        return
    _send_image(client, png, image.get_width(), image.get_height())

func _state() -> Dictionary:
    var size: Vector2 = get_viewport().get_visible_rect().size
    return {
        "status":"ok",
        "engine":"Godot",
        "port":listening_port,
        "viewportWidth":int(size.x),
        "viewportHeight":int(size.y),
        "framebuffer":"Godot Viewport.get_texture().get_image()",
        "input":"Godot Input.parse_input_event()"
    }

func _handle_input(client: StreamPeerTCP, query: Dictionary) -> void:
    var event_type: String = str(query.get("type", ""))
    var x: float = float(query.get("x", "0"))
    var y: float = float(query.get("y", "0"))
    match event_type:
        "click":
            var button: MouseButton = _button_index(str(query.get("button", "left")))
            _mouse_button(x, y, button, true, _as_bool(query.get("double", "false")))
            _mouse_button(x, y, button, false, false)
        "tap":
            var touch_index: int = int(query.get("index", "0"))
            _touch(x, y, touch_index, true)
            _touch(x, y, touch_index, false)
        "mouse_button":
            _mouse_button(x, y, _button_index(str(query.get("button", "left"))), _as_bool(query.get("pressed", "false")), _as_bool(query.get("double", "false")))
        "mouse_motion":
            _mouse_motion(x, y, float(query.get("relative_x", "0")), float(query.get("relative_y", "0")))
        "touch":
            _touch(x, y, int(query.get("index", "0")), _as_bool(query.get("pressed", "false")))
        "key":
            _key(query)
        "action":
            var action: String = str(query.get("action", ""))
            if action.is_empty():
                _send_json(client, 400, {"status":"error","message":"action is required"})
                return
            if _as_bool(query.get("pressed", "false")):
                Input.action_press(action, float(query.get("strength", "1.0")))
            else:
                Input.action_release(action)
        _:
            _send_json(client, 400, {"status":"error","message":"unsupported input type"})
            return
    _send_json(client, 200, {"status":"ok","engine":"Godot","input":event_type})

func _mouse_button(x: float, y: float, button_index: MouseButton, pressed: bool, double_click: bool) -> void:
    var event: InputEventMouseButton = InputEventMouseButton.new()
    event.position = Vector2(x, y)
    event.global_position = event.position
    event.button_index = button_index
    event.pressed = pressed
    event.double_click = double_click
    event.factor = 1.0
    Input.parse_input_event(event)

func _mouse_motion(x: float, y: float, relative_x: float, relative_y: float) -> void:
    var event: InputEventMouseMotion = InputEventMouseMotion.new()
    event.position = Vector2(x, y)
    event.global_position = event.position
    event.relative = Vector2(relative_x, relative_y)
    event.screen_relative = event.relative
    event.velocity = event.relative
    event.screen_velocity = event.velocity
    Input.parse_input_event(event)

func _touch(x: float, y: float, index: int, pressed: bool) -> void:
    var event: InputEventScreenTouch = InputEventScreenTouch.new()
    event.position = Vector2(x, y)
    event.index = index
    event.pressed = pressed
    Input.parse_input_event(event)

func _key(query: Dictionary) -> void:
    var event: InputEventKey = InputEventKey.new()
    event.keycode = int(query.get("keycode", "0"))
    event.physical_keycode = int(query.get("physical_keycode", "0"))
    event.unicode = int(query.get("unicode", "0"))
    event.pressed = _as_bool(query.get("pressed", "false"))
    event.echo = false
    Input.parse_input_event(event)

func _button_index(name: String) -> MouseButton:
    match name.to_lower():
        "left", "1":
            return MOUSE_BUTTON_LEFT
        "right", "2":
            return MOUSE_BUTTON_RIGHT
        "middle", "3":
            return MOUSE_BUTTON_MIDDLE
        "wheel_up":
            return MOUSE_BUTTON_WHEEL_UP
        "wheel_down":
            return MOUSE_BUTTON_WHEEL_DOWN
        _:
            return MOUSE_BUTTON_LEFT

func _as_bool(value) -> bool:
    return str(value).to_lower() in ["1","true","yes","on"]

func _send_json(client: StreamPeerTCP, code: int, payload: Dictionary) -> void:
    _write_response(client, code, "application/json", JSON.stringify(payload).to_utf8_buffer())

func _send_image(client: StreamPeerTCP, png: PackedByteArray, width: int, height: int) -> void:
    var header: String = "HTTP/1.1 200 OK\r\nContent-Type: image/png\r\nContent-Length: %d\r\nConnection: close\r\nX-Godot-Viewport-Width: %d\r\nX-Godot-Viewport-Height: %d\r\n\r\n" % [png.size(), width, height]
    client.put_data(header.to_utf8_buffer())
    client.put_data(png)
    client.disconnect_from_host()

func _write_response(client: StreamPeerTCP, code: int, content_type: String, body: PackedByteArray) -> void:
    var phrase: String = "OK"
    if code == 400:
        phrase = "Bad Request"
    elif code == 404:
        phrase = "Not Found"
    elif code == 405:
        phrase = "Method Not Allowed"
    elif code == 429:
        phrase = "Too Many Requests"
    elif code >= 500:
        phrase = "Internal Server Error"
    var header: String = "HTTP/1.1 %d %s\r\nContent-Type: %s\r\nContent-Length: %d\r\nConnection: close\r\n\r\n" % [code, phrase, content_type, body.size()]
    client.put_data(header.to_utf8_buffer())
    client.put_data(body)
    client.disconnect_from_host()
