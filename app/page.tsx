const commands = [
  "get-global-project",
  "set-global-project",
  "create-template",
  "create-from-template",
  "register",
  "register-show",
  "get-registered",
  "enable-gem",
  "disable-gem",
  "edit-engine-properties",
  "edit-project-properties",
  "edit-gem-properties",
  "sha256",
  "download",
  "export-project-configure",
  "export-project",
  "repo",
  "edit-repo-properties",
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
        Streamable HTTP MCP hosted on Vercel for the Open 3D Engine (O3DE).
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
      <p>
        The MCP mirrors the first-party subcommands registered by{" "}
        <code>scripts/o3de.py</code>.
      </p>

      <h2>Exposed CLI tools</h2>
      <ul>
        {commands.map((command) => (
          <li key={command}>
            <code>o3de_{command.replaceAll("-", "_")}</code>
          </li>
        ))}
      </ul>

      <h2>Execution model</h2>
      <p>
        Vercel hosts the MCP protocol layer. The actual O3DE process runs in a
        separate HTTP bridge because Vercel Functions do not provide a persistent
        O3DE engine installation.
      </p>
    </main>
  );
}
