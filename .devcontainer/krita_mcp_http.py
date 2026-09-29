import os
import sys

sys.path.insert(0, "/opt/krita-mcp")

from server import mcp


if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
        host="127.0.0.1",
        port=19797,
    )
