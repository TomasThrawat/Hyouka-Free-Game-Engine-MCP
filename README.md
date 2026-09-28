# Hyouka Godot MCP

Vercel Streamable HTTP MCP gateway for the official Godot Engine.

Official repository: https://github.com/godotengine/godot

Runtime: **Godot 4.7.2-stable Linux x86_64**, downloaded from the official GitHub release and SHA-256 verified.

The MCP exposes dynamic Godot CLI discovery plus universal invocation, project run/import/check, editor launch, release/debug export, scripts, process control, and CLI help.

GitHub Actions can start a temporary real Godot runtime, expose the bridge through HTTPS, publish the URL to runtime/godot-bridge.json, and clear it when the job ends.
