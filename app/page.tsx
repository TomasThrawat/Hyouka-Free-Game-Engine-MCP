const capabilities = [
  "Dynamic Python tool discovery",
  "Shell-script discovery",
  "Built executable discovery",
  "O3DE CLI discovery",
  "CMake executable/custom targets",
  "CTest registrations",
  "Help probing",
  "Universal tool invocation",
  "Background process control",
  "CMake builds",
];

export default function Home() {
  return (
    <main
      style={{
        maxWidth: 960,
        margin: "40px auto",
        padding: "0 20px",
        fontFamily: "system-ui, sans-serif",
        lineHeight: 1.5,
      }}
    >
      <h1>Hyouka O3DE MCP</h1>
      <p>
        Streamable HTTP MCP hosted on Vercel for the open-source Open 3D Engine
        (O3DE).
      </p>
      <p>
        MCP endpoint: <code>/api/mcp</code>
      </p>

      <h2>Engine</h2>
      <p>
        Source:{" "}
        <a href="https://github.com/o3de/o3de" target="_blank" rel="noreferrer">
          github.com/o3de/o3de
        </a>
      </p>

      <h2>Dynamic tool gateway</h2>
      <p>
        The bridge discovers callable O3DE tooling from the installed engine
        tree instead of limiting the MCP to top-level CLI commands.
      </p>
      <ul>
        {capabilities.map((capability) => (
          <li key={capability}>{capability}</li>
        ))}
      </ul>

      <h2>Execution model</h2>
      <p>
        Vercel hosts the MCP protocol layer. The actual O3DE process runs in a
        separate HTTPS bridge host with O3DE installed.
      </p>
      <p>
        Internal C++ classes and APIs that are not independently callable are
        not fabricated into fake MCP tools.
      </p>
    </main>
  );
}
