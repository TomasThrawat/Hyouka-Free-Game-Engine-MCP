import { createMcpHandler } from "mcp-handler";
import * as z from "zod/v4";
const CONFIG="https://raw.githubusercontent.com/TomasThrawat/Hyouka-Free-Game-Engine-MCP/main/runtime/godot-bridge.json";
async function base(){if(process.env.GODOT_BRIDGE_URL)return process.env.GODOT_BRIDGE_URL.replace(/\/$/,"");try{const r=await fetch(CONFIG+"?t="+Date.now(),{cache:"no-store"});const x=await r.json();return x.status==="ok"&&x.url?String(x.url).replace(/\/$/,""):null}catch{return null}}
async function call(path:string,body?:any){const b=await base();if(!b)return{status:"not_configured",engine:"Godot",config:CONFIG};try{const r=await fetch(b+path,{method:body?"POST":"GET",headers:body?{"content-type":"application/json"}:undefined,body:body?JSON.stringify(body):undefined,cache:"no-store"});const t=await r.text();let x;try{x=JSON.parse(t)}catch{x={status:"error",message:t}}return r.ok?x:{status:"error",httpStatus:r.status,...x}}catch(e){return{status:"error",message:String(e)}}}
const out=(x:any)=>({content:[{type:"text" as const,text:JSON.stringify(x,null,2)}]});
const common=z.object({args:z.array(z.string().max(4096)).max(128).default([]),cwd:z.string().max(2048).optional(),timeoutSeconds:z.number().int().min(1).max(600).optional(),background:z.boolean().optional()});
const handler=createMcpHandler(server=>{
 server.registerTool("godot_status",{description:"Check the live Godot runtime."},async()=>out(await call("/health")));
 server.registerTool("godot_discover_tools",{description:"Discover Godot CLI tools and flags."},async()=>out(await call("/discover")));
 server.registerTool("godot_find_tools",{description:"Search the Godot tool inventory.",inputSchema:z.object({query:z.string().optional()})},async({query})=>out(await call("/find?q="+encodeURIComponent(query||""))));
 server.registerTool("godot_invoke_tool",{description:"Invoke any discovered Godot tool.",inputSchema:z.object({toolId:z.string(),...common.shape})},async(x)=>out(await call("/invoke",x)));
 for(const [id,title] of [["godot-run-project","Run a Godot project"],["godot-editor","Launch the Godot editor"],["godot-import","Import Godot resources"],["godot-check","Validate a Godot project"],["godot-export-release","Export a release build"],["godot-export-debug","Export a debug build"],["godot-script","Run a Godot script"]] as const)
  server.registerTool(id,{description:title,inputSchema:common},async(x)=>out(await call("/invoke",{...x,toolId:id})));
 server.registerTool("godot_processes",{description:"List bridge-managed processes."},async()=>out(await call("/processes")));
 server.registerTool("godot_stop_process",{description:"Stop a bridge-managed process.",inputSchema:z.object({pid:z.number().int().positive()})},async(x)=>out(await call("/stop",x)));
 server.registerTool("godot_cli_help",{description:"Show Godot CLI help."},async()=>out(await call("/help")));
});
export {handler as GET,handler as POST};
