# Hyouka Godot MCP

Vercel Streamable HTTP MCP gateway for the official Godot Engine.

Official repository: https://github.com/godotengine/godot

Runtime: **Godot 4.7.2-stable .NET Linux x86_64**, downloaded from the official GitHub release and SHA-512 verified.

## Official Godot tool coverage

This MCP uses the official Godot Engine repository as the source of truth for the Godot 4.7.2-stable command-line surface.

- 115 official CLI switches from main/main.cpp are shipped as first-class discovered MCP tools.
- The bridge also checks the installed binary's --help output for any additional runtime switches not already in the official manifest.
- Stable gateway tools provide universal invocation, discovery, and runtime health.
- Additional inspection tools expose Godot's public ClassDB class list, class metadata (methods/properties/signals/enums), and headless PackedScene scene trees.

The 115-switch manifest is stored at runtime/godot-official-cli.json and records the source repository, ref, source file, version, and exact switches.

This does not pretend that every internal/private C++ function is a tool. Godot exposes hundreds of public engine/editor classes and thousands of methods; those are covered through reflection/inspection tools instead of creating thousands of duplicate MCP registrations.

## Dynamic Godot tools

The MCP reads the live bridge inventory and automatically registers every discovered callable tool with the MCP server.

Stable gateway tools:

- godot_invoke_tool
- godot_discover_tools
- godot_status

Bridge inspection tools include:

- godot-class-list
- godot-class-info
- godot-scene-tree

The current design keeps everything in this single MCP and is compatible with MCP tool-list refresh/synchronization.

## Source

- https://github.com/godotengine/godot/tree/4.7.2-stable
- CLI source: main/main.cpp
