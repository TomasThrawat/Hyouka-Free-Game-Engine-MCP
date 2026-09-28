# Hyouka Free Game Engine MCP

No-PC, free-first game-engine MCP stack.

Architecture:
Android browser -> Composio -> public HTTPS MCP on Vercel -> GitHub Codespaces / browser-native game editors

Enabled browser engines:
- Godot Web Editor: https://editor.godotengine.org/
- GDevelop: https://editor.gdevelop.io/
- Construct 3: https://editor.construct.net/

GitHub Codespaces is used for source editing and CPU-based builds.

Free-only policy:
This project does not advertise a GPU cloud desktop as free unless its current terms are verified. Unity/Unreal are therefore listed as not provisioned in the MCP manifest.

MCP endpoint after deployment:
https://YOUR-VERCEL-DOMAIN/api/mcp

Tools:
- list_free_web_engines
- get_web_engine_url
- free_stack_manifest
- codespaces_bootstrap
- desktop_engine_status
