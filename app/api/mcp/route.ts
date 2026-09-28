import { createMcpHandler } from "mcp-handler";
import * as z from "zod/v4";

const engines = {
  godot:{name:"Godot Web Editor",url:"https://editor.godotengine.org/",mode:"web"},
  gdevelop:{name:"GDevelop Web Editor",url:"https://editor.gdevelop.io/",mode:"web"},
  construct:{name:"Construct 3",url:"https://editor.construct.net/",mode:"web"}
} as const;

const handler = createMcpHandler((server) => {
  server.registerTool(
    "list_free_web_engines",
    {
      title:"List Free Web Engines",
      description:"List the browser-native game engines enabled for the no-PC free stack."
    },
    async () => ({
      content:[{
        type:"text",
        text:JSON.stringify({
          policy:"free-only-no-pc",
          engines:Object.entries(engines).map(([id,value])=>({id,...value})),
          note:"These are web editors. No GPU cloud desktop is assumed."
        },null,2)
      }]
    })
  );

  server.registerTool(
    "get_web_engine_url",
    {
      title:"Get Web Engine URL",
      description:"Return the official web editor URL for one enabled engine.",
      inputSchema:z.object({engine:z.enum(["godot","gdevelop","construct"])})
    },
    async ({engine}) => ({
      content:[{
        type:"text",
        text:JSON.stringify({id:engine,...engines[engine]},null,2)
      }]
    })
  );

  server.registerTool(
    "free_stack_manifest",
    {
      title:"Free Stack Manifest",
      description:"Return the complete no-PC architecture and free-resource boundaries."
    },
    async () => ({
      content:[{
        type:"text",
        text:JSON.stringify({
          layers:{
            control:"Composio/custom MCP",
            mcpHosting:"Vercel free deployment",
            cloudDev:"GitHub Codespaces",
            browserEngines:Object.keys(engines),
            desktopGpuEngines:[]
          },
          codespaces:{
            includedForPersonalFreeAccounts:"120 core-hours/month and 15 GB-month storage",
            spendingPolicy:"do not rely on paid overage"
          },
          rule:"Only verified free/no-card paths are included in this manifest."
        },null,2)
      }]
    })
  );

  server.registerTool(
    "codespaces_bootstrap",
    {
      title:"Codespaces Bootstrap",
      description:"Return cloud-only commands used inside GitHub Codespaces to install and build this project."
    },
    async () => ({
      content:[{
        type:"text",
        text:[
          "git clone https://github.com/TomasThrawat/Hyouka-Free-Game-Engine-MCP.git",
          "cd Hyouka-Free-Game-Engine-MCP",
          "npm install",
          "npm run build"
        ].join("\n")
      }]
    })
  );

  server.registerTool(
    "desktop_engine_status",
    {
      title:"Desktop Engine Status",
      description:"Explain which desktop engines are intentionally not provisioned under the free no-PC policy.",
      inputSchema:z.object({engine:z.enum(["unity","unreal"])})
    },
    async ({engine}) => ({
      content:[{
        type:"text",
        text:JSON.stringify({
          engine,
          status:"not-provisioned",
          reason:"A free GPU-backed desktop runtime was not assumed or advertised without current verification.",
          alternative:"Use the enabled browser engines or GitHub Codespaces for source/build work."
        },null,2)
      }]
    })
  );
});

export { handler as GET, handler as POST };
