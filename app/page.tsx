const engines = [
  ["Godot Web Editor", "https://editor.godotengine.org/"],
  ["GDevelop", "https://editor.gdevelop.io/"],
  ["Construct 3", "https://editor.construct.net/"],
] as const;

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
      <h1>Hyouka Free Game Engine MCP</h1>
      <p>
        Mobile-first free stack: Vercel Streamable HTTP MCP + GitHub Codespaces +
        browser-native engines + headless Blender.
      </p>
      <p>
        MCP endpoint: <code>/api/mcp</code>
      </p>
      <h2>Browser engines</h2>
      <ul>
        {engines.map(([name, url]) => (
          <li key={name}>
            <a href={url} target="_blank" rel="noreferrer">
              {name}
            </a>
          </li>
        ))}
      </ul>
      <h2>Blender</h2>
      <p>
        Blender runs headless in GitHub Codespaces on CPU. The Vercel MCP exposes
        scene, object, save, render, and GLB export tools.
      </p>
      <h2>Cost boundary</h2>
      <p>
        This project intentionally does not provision paid GPU cloud, paid overage,
        Unity cloud editors, or Unreal cloud editors.
      </p>
    </main>
  );
}
