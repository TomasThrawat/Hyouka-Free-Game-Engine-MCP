#!/usr/bin/env python3
import json, os, re, signal, subprocess, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
HOST=os.getenv("GODOT_BRIDGE_HOST","0.0.0.0"); PORT=int(os.getenv("GODOT_BRIDGE_PORT","9765"))
GODOT=Path(os.getenv("GODOT_BIN","/opt/godot/4.7.2/godot")).resolve(); ROOT=Path(os.getenv("GODOT_WORKSPACE_ROOT",Path.cwd())).resolve(); PROCS={}
def inside(p=None):
 x=(ROOT if not p else Path(p).expanduser().resolve()); x.relative_to(ROOT)
 if not x.exists(): raise ValueError("path does not exist")
 return x
def args_ok(a):
 if not isinstance(a,list) or len(a)>128: raise ValueError("args must be a list of <=128 strings")
 if any(not isinstance(x,str) or "\x00" in x or len(x)>4096 for x in a): raise ValueError("invalid argument")
 return a
def normalize(a):
 a=args_ok(a); out=[]; i=0
 while i<len(a):
  out.append(a[i])
  if a[i] in ("--path","-p"):
   if i+1>=len(a): raise ValueError("--path requires a value")
   out.append(str(inside(a[i+1]))); i+=2
  else: i+=1
 return out
def run(args,cwd=None,timeout=120,bg=False):
 a=normalize(args); wd=inside(cwd); cmd=[str(GODOT)]+a
 if bg:
  p=subprocess.Popen(cmd,cwd=wd,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,shell=False,start_new_session=True)
  PROCS[p.pid]=(p,time.time(),cmd,str(wd)); return {"status":"started","pid":p.pid,"command":cmd,"cwd":str(wd)}
 p=subprocess.run(cmd,cwd=wd,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,shell=False,timeout=min(max(int(timeout),1),600))
 return {"status":"ok" if p.returncode==0 else "failed","returnCode":p.returncode,"stdout":p.stdout[-24000:],"stderr":p.stderr[-24000:],"command":cmd,"cwd":str(wd)}
def tools():
 base=[("godot-cli","Run any Godot CLI arguments."),("godot-run-project","Run a Godot project."),("godot-editor","Launch the editor."),("godot-import","Import project resources."),("godot-check","Validate a project."),("godot-export-release","Export a release preset."),("godot-export-debug","Export a debug preset."),("godot-script","Run a Godot script.")]
 out=[{"id":i,"kind":"godot","callable":True,"description":d} for i,d in base]
 try:
  h=subprocess.run([str(GODOT),"--help"],capture_output=True,text=True,timeout=30,shell=False)
  for f in sorted(set(re.findall(r"(?<![\w-])(--[a-z0-9][a-z0-9-]*)",h.stdout+h.stderr))): out.append({"id":"godot-flag:"+f[2:],"kind":"godot-cli-flag","callable":True,"flag":f,"description":"Flag discovered from Godot --help"})
 except Exception: pass
 return out
def invoke(t,a,cwd=None,timeout=120,bg=False):
 if t=="godot-run-project" and "--path" not in a and "-p" not in a: a=["--path",str(ROOT)]+a
 elif t=="godot-editor" and "--editor" not in a: a=["--editor"]+a
 elif t in ("godot-import","godot-check"): a=["--headless","--editor","--quit"]+a
 elif t.startswith("godot-flag:"): a=["--"+t.split(":",1)[1]]+a
 elif t in {"godot-export-release","godot-export-debug","godot-script"}:
  required={"godot-export-release":"--export-release","godot-export-debug":"--export-debug","godot-script":"--script"}[t]
  if required not in a: raise ValueError("args must contain "+required)
 return run(a,cwd,timeout,bg)
class H(BaseHTTPRequestHandler):
 def send(self,code,obj):
  b=json.dumps(obj,separators=(",",":")).encode(); self.send_response(code); self.send_header("Content-Type","application/json"); self.send_header("Content-Length",str(len(b))); self.send_header("Access-Control-Allow-Origin","*"); self.end_headers(); self.wfile.write(b)
 def body(self):
  n=int(self.headers.get("Content-Length","0"))
  if n>200000: raise ValueError("body too large")
  return json.loads(self.rfile.read(n) or b"{}")
 def do_GET(self):
  try:
   p=urlparse(self.path)
   if p.path=="/health":
    v=subprocess.run([str(GODOT),"--version"],capture_output=True,text=True,timeout=30,shell=False)
    return self.send(200,{"status":"ok","engine":"Godot","version":v.stdout.strip(),"toolCount":len(tools())})
   if p.path=="/discover": return self.send(200,{"status":"ok","engine":"Godot","tools":tools()})
   if p.path=="/find":
    q=parse_qs(p.query).get("q",[""])[0].lower(); return self.send(200,{"status":"ok","tools":[x for x in tools() if q in json.dumps(x).lower()]})
   if p.path=="/help": return self.send(200,run(["--help"],timeout=30))
   if p.path=="/processes": return self.send(200,{"status":"ok","processes":[{"pid":pid,"running":x[0].poll() is None,"startedAt":x[1],"command":x[2],"cwd":x[3]} for pid,x in PROCS.items()]})
   if p.path=="/selftest":
    r=run(["--headless","--path",str(ROOT/"runtime/godot-smoke-test"),"--editor","--quit"],timeout=120); return self.send(200,{"status":"ok" if r["status"]=="ok" else "failed","smokeTest":r})
   return self.send(404,{"status":"error","error":"not_found"})
  except Exception as e: return self.send(500,{"status":"error","message":str(e)})
 def do_POST(self):
  try:
   p=urlparse(self.path).path; b=self.body()
   if p=="/invoke": return self.send(200,invoke(str(b["toolId"]),b.get("args",[]),b.get("cwd"),b.get("timeoutSeconds",120),bool(b.get("background"))))
   if p=="/stop":
    pid=int(b["pid"]); x=PROCS.get(pid)
    if not x: raise ValueError("unknown process")
    if x[0].poll() is None: os.killpg(x[0].pid,signal.SIGTERM)
    PROCS.pop(pid,None); return self.send(200,{"status":"stopped","pid":pid})
   return self.send(404,{"status":"error","error":"not_found"})
  except subprocess.TimeoutExpired: return self.send(408,{"status":"timeout"})
  except Exception as e: return self.send(400,{"status":"error","message":str(e)})
 def log_message(self,*a): pass
if __name__=="__main__":
 if not GODOT.is_file(): raise SystemExit("Godot binary not found: "+str(GODOT))
 ThreadingHTTPServer((HOST,PORT),H).serve_forever()
