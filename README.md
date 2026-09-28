# Hyouka Godot MCP

Vercel Streamable HTTP MCP gateway for the official Godot Engine.

Official repository: https://github.com/godotengine/godot

Runtime: **Godot 4.7.2-stable .NET Linux x86_64**, downloaded from the official GitHub release and SHA-512 verified.

The .NET-enabled Godot editor adds C# scripting support. GitHub Actions installs the 64-bit .NET SDK before downloading and running the .NET Godot runtime.

## Dynamic Godot tools

The MCP no longer hardcodes a separate registration for every Godot command.

At MCP request time, it reads the live bridge's /discover inventory and automatically registers every discovered callable tool with the MCP server. The inventory is refreshed every 15 seconds and can also be forced through the godot_discover_tools gateway tool.

This means newly discovered Godot CLI tools and flags become MCP tools without adding another registerTool block.

There are also three small stable gateway tools:

- godot_invoke_tool: universal fallback for any discovered tool id.
- godot_discover_tools: refresh and inspect the complete bridge inventory.
- godot_status: check the live runtime.

The dynamic surface currently covers the tools exposed by the bridge, including Godot CLI commands and flags discovered from Godot --help. It does not claim to expose every private/internal Godot Editor API.
