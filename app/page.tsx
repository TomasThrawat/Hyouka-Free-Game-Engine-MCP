const engines = [
  ["Godot Web Editor", "https://editor.godotengine.org/"],
  ["GDevelop", "https://editor.gdevelop.io/"],
  ["Construct 3", "https://editor.construct.net/"]
] as const;

export default function Home() {
  return (
    <main style={{maxWidth:900,margin:"40px auto",padding:"0 20px",fontFamily:"system-ui,sans-serif"}}>
      <h1>Hyouka Free Game Engine MCP</h1>
      <p>Mobile-only stack: Vercel MCP + GitHub Codespaces + browser-native engines.</p>
      <p>MCP endpoint: <code>/api/mcp</code></p>
      <h2>Web engines</h2>
      <ul>{engines.map(([name,url])=><li key={name}><a href={url} target="_blank" rel="noreferrer">{name}</a></li>)}</ul>
      <h2>Free runtime policy</h2>
      <p>No paid GPU runtime is assumed. Desktop engines are not exposed as runnable cloud editors by this server.</p>
    </main>
  );
}
