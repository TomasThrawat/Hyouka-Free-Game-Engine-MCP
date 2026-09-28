# Hyouka Godot MCP

Vercel Streamable HTTP MCP gateway for the official Godot Engine.

Official repository: https://github.com/godotengine/godot

Runtime: **Godot 4.7.2-stable .NET Linux x86_64**, downloaded from the official GitHub release and SHA-512 verified.

The .NET-enabled Godot editor adds C# scripting support. GitHub Actions installs the 64-bit .NET SDK before downloading and running the .NET Godot runtime.

The MCP exposes dynamic Godot CLI discovery plus universal invocation, project run/import/check, editor launch, release/debug export, scripts, process control, and CLI help.

GitHub Actions can start a temporary real Godot runtime, expose the bridge through HTTPS, publish the URL to runtime/godot-bridge.json, and clear it when the job ends.
