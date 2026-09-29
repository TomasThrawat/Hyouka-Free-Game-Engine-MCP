extends Node

func _ready() -> void:
    var version_info := Engine.get_version_info()
    assert(version_info.major == 4)
    assert(version_info.minor == 7)
    assert(version_info.patch == 2)
    assert(ProjectSettings.get_setting("application/config/name") == "Hyouka Godot MCP Smoke Test")
    print("Godot runtime smoke test passed: " + str(version_info.string))
    get_tree().quit()
