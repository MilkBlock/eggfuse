"""Local, lazy Graphviz rendering for large catalogs and native before/after states."""
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import hashlib
import json
import webbrowser
from urllib.parse import urlsplit

from . import _load
from .egraph import layout_graph, snapshot_graph, svg


def library(path, program):
    p = Path(path)
    file = p / "catalog.json" if p.is_dir() else p
    if file.is_file() and file.name not in ("ripen.json","trigger-state.json","observed-saturated-state.json"):
        data = _load(file)
        units = data if isinstance(data,list) else data["layouts"]
        donor = Path(program) if program else file.parent.parent / "sum/program.json"
        recipe = _load(donor)["recipe"]
        rules = recipe["rules"]
        signatures = data.get("signatures") if isinstance(data,dict) else None
        fixed = file.with_name("fixed.json")
        if not signatures and fixed.exists():
            info=_load(fixed)
            if info.get("catalog")==hashlib.sha256(file.read_bytes()).hexdigest():
                signatures=info["signatures"]
        if signatures:
            by_sig={hashlib.sha256(json.dumps(r,sort_keys=True).encode()).hexdigest():r for r in rules}
            rules=[by_sig.get(s) for s in signatures]
            if any(rules[r] is None for u in units for r,_,_ in u):
                raise ValueError("donor program does not contain the catalog's rule signatures")
        constructors={t["name"] for t in recipe["tables"] if t["kind"]=="constructor"}
        return (dict(name=file.parent.name,mode="符号模板",count=len(units)),
                lambda i,phase: layout_graph(units[i],rules,constructors))
    base=p if p.is_dir() else p.parent
    folders=sorted(f.parent for f in base.rglob("ripen.json") if (f.parent/"observed-saturated-state.json").exists())
    if not folders:
        raise ValueError(f"No Ripen state exports found in {base}")
    names=[str(f.relative_to(base)) if f!=base else f.name for f in folders]
    return (dict(name=base.name,mode="原生快照",count=len(names),names=names),
            lambda i,phase: snapshot_graph(folders[i]/("trigger-state.json" if phase=="before" else "observed-saturated-state.json")))


def serve(paths,program,port,launch):
    libs=[library(p,program) for p in paths]
    page=Path(__file__).with_name("egraph.html").read_text(encoding="utf-8")
    page=page.replace("/*LIBRARIES*/",json.dumps([x[0] for x in libs],ensure_ascii=False).replace("<","\\u003c"))
    @lru_cache(maxsize=24)
    def draw(k,i,phase):
        g=libs[k][1](i,phase)
        return json.dumps(dict(svg=svg(g),notes=g.notes),ensure_ascii=False)
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path=urlsplit(self.path).path
            if path=="/":
                body,mime=page,"text/html"
            else:
                try:
                    prefix,cat,cell,phase=path.strip("/").split("/")
                    k,i=int(cat),int(cell)
                    if prefix!="graph" or k<0 or k>=len(libs) or not 0<=i<libs[k][0]["count"] or phase not in ("before","after"):
                        raise ValueError("Unknown Cell")
                    body,mime=draw(k,i,phase),"application/json"
                except Exception as error:
                    self.send_error(422,str(error).encode("ascii","replace").decode())
                    return
            encoded=body.encode()
            self.send_response(200)
            self.send_header("Content-Type",mime+"; charset=utf-8")
            self.send_header("Content-Length",str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
    with ThreadingHTTPServer(("127.0.0.1",port),Handler) as server:
        url="http://127.0.0.1:%d/"%server.server_port
        print(url,flush=True)
        if launch:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
