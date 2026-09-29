from dcc_mcp_core import McpHttpConfig, McpHttpServer, ToolRegistry
from dcc_mcp_core.host import BlockingDispatcher
from dcc_mcp_blender import BlenderHost


def main() -> None:
    registry = ToolRegistry()
    config = McpHttpConfig(
        host="127.0.0.1",
        port=18765,
        server_name="hyouka-blender",
    )
    server = McpHttpServer(registry, config)
    dispatcher = BlockingDispatcher()
    server.attach_dispatcher(dispatcher)
    handle = server.start()
    print(f"MCP_URL={handle.mcp_url()}", flush=True)
    BlenderHost(dispatcher).run_headless()


if __name__ == "__main__":
    main()
