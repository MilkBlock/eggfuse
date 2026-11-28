"""Paid-prefix native curves. Counterfactual effect probes run after independent generation."""
import gzip
import hashlib
import json
import os
import re
import sqlite3
import sys
import tempfile
import subprocess
from collections import defaultdict
from pathlib import Path
from time import perf_counter

import torch

from binding_egg import unpack
from ccp_v01 import Client
from credit_scale_buffer import submit
from discrete_draft import Cell
from exposure_data import observed
from exposure_policy import policy
from exposure_train import output, sha
from exposure_worlds import HELD
from int_parameters import digest
from partner_index_worlds import args
from scaling_archive import directory
from scaling_eval import HeldoutLedger

BUDGETS = (16, 32, 64, 128, 256)


class Database:
    def __init__(self, path):
        self.db = sqlite3.connect(path, timeout=120)
        self.db.execute("CREATE TABLE IF NOT EXISTS evidence (kind TEXT, key TEXT, data BLOB, PRIMARY KEY(kind,key))")

    def get(self, kind, key):
        r = self.db.execute("SELECT data FROM evidence WHERE kind=? AND key=?", (kind, key)).fetchone()
        return json.loads(gzip.decompress(r[0])) if r else None

    def put(self, kind, key, value):
        data = gzip.compress(json.dumps(value, separators=(",", ":")).encode(), compresslevel=2)
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO evidence VALUES(?,?,?)", (kind,key,data))


class SourcePanic(RuntimeError):
    """Only a panic explicitly emitted by the native source program."""
    def __init__(self, evidence):
        super().__init__(evidence["stderr"])
        self.evidence = evidence


def is_source_panic(stderr):
    return re.search(r'^Error: "source panic \(Run [0-9]+, rule [0-9]+, op [0-9]+,', stderr, re.M) is not None


class Trials:
    def __init__(self,a,db,case,name,seed,unique):
        self.a,self.db,self.seed=a,db,seed
        self.policy,self.w,self.align=policy(a,case,name,unique)
        self.ir=self.w.dir/"program.json"
        self.program=sha(self.ir)
        self.condition=dict(case=case,model=name,seed=seed,unique=unique,program=self.program)
        if name not in ("history","random"):
            if "/" in name:
                group,tag=name.split("/")
                weights=output(a)/group/(tag+".pt")
            else:
                weights=directory(a)/"fits"/(name+".pt")
            self.condition["weights"]=sha(weights)

    def trial(self, cap):
        k=digest([self.condition,cap])
        result=self.db.get("trial",k)
        if result is None:
            failed = self.db.get("native_panic", k)
            if failed:
                raise SourcePanic(failed)
            tr = HeldoutLedger()
            with tempfile.TemporaryFile() as err:
                try:
                    r, tr = observed(self.w, self.align, self.a, self.policy, self.seed,
                                     cap, trace=tr, native_stderr=err)
                except (RuntimeError, OSError, EOFError, ValueError) as exc:
                    err.seek(0)
                    message = err.read().decode(errors="replace")
                    if not is_source_panic(message):
                        print(message, file=sys.stderr)
                        raise
                    failed = dict(condition=self.condition, cap=cap, stderr=message,
                                  observed_replies=tr.responses)
                    self.db.put("native_panic", k, failed)
                    print(self.condition["case"], self.condition["model"], self.seed, cap,
                          message.strip(), file=sys.stderr, flush=True)
                    raise SourcePanic(failed) from exc
            requests=tr.responses
            by_uid={v["uid"]:v["effective_ops"] for v in tr.entries.values()}
            owner={u:u for u in by_uid}
            for root,h in tr.higher.items():
                for step in h["steps"]:
                    by_uid[step["uid"]]=step["effective_ops"]
                    owner[step["uid"]]=root
            rows=[]
            for run,epoch,tid,refs,reply in requests:
                uid=reply[0]; oid=owner[uid]
                item=tr.entries[oid]
                complete=oid not in tr.higher or tr.higher[oid]["completed"]
                rows.append(dict(run=run,epoch=epoch,tid=tid,refs=refs,reply=reply,owner=oid,
                                 ops=by_uid[uid],name=[item["tid"],item["refs"]],complete=complete))
            if len(rows)!=r["stats"].get("paid",0) or sum(v["ops"] for v in rows)!=r["ops"]:
                raise ValueError("native paid or effective-operation accounting differs")
            result=dict(condition=self.condition,cap=cap,r=r,requests=rows)
            self.db.put("trial",k,result)
            result=self.db.get("trial",k)
        return result

    def effect(self, requests):
        tape=[[r["run"],r["epoch"],r["tid"],r["refs"],r["reply"]] for r in requests]
        key=digest([self.program,self.seed,tape])
        data=self.db.get("prefix",key)
        if data is not None:
            return data
        a,w=self.a,self.w
        export=a.native_export_dir/"prefix.json"
        by_run=defaultdict(list)
        for r in requests:
            by_run[r["run"]].append(r)
        cmd=[a.runtime_binary,"online-ccp-v0.1",self.ir,"-","audit","--export",export,
             "--ept-origins","--address-seed",str(self.seed*11+513)]
        with subprocess.Popen(cmd,stdin=-1,stdout=-1) as proc:
            client=Client(proc,512,self.program)
            try:
                for line in iter(proc.stdout.readline,b""):
                    f=json.loads(line)
                    if "role" in f: break
                    unpack(proc.stdout,f)
                    if f.get("final_publication"):continue
                    client.run,client.epoch=f["run"],f["epoch"]
                    group=by_run.pop(client.run,[])
                    if group:
                        cells=[Cell(w.layouts[r["tid"]][0][0],tuple(map(tuple,r["refs"]))) for r in group]
                        replies=submit(client,cells,64)
                        if any(list(out)!=r["reply"] or r["epoch"]!=client.epoch
                               for r,out in zip(group,replies,strict=True)):
                            raise ValueError("offline prefix changed a named request or receipt")
                    client.seal()
                if proc.wait() or by_run or "role" not in f:
                    raise ValueError("offline prefix did not finish the native schedule")
            finally:
                client.close()
        facts,goal=self.align(json.loads(export.read_text()))
        if not facts<=goal:
            raise ValueError("unexpected reference fact")
        data=dict(facts=sorted(facts),graph=f["state_sha"],ops=sum(dict(f["ept"]["origins"]).values()))
        self.db.put("prefix",key,data)
        return data

    def run(self):
        # First signed positive paid operation may follow zero-credit admissions.
        first = None
        for limit in (257, 1, *BUDGETS, None):
            try:
                probe = self.trial(limit)
            except SourcePanic:
                continue
            first = next((i for i, r in enumerate(probe["requests"], 1) if r["ops"] > 0), None)
            if first is not None or limit is None:
                break
        anchor=self.trial(first) if first is not None else None
        rows=[]
        for cap in BUDGETS:
            for mode in ("total","continuation"):
                requested=cap if mode=="total" else (first+cap if first is not None else None)
                try:
                    x=self.trial(requested)
                except SourcePanic as error:
                    self.db.put("failed_budget", digest([self.condition, mode, cap]),
                                dict(**self.condition, mode=mode, budget=cap, first=first,
                                     cap=requested, observed_replies=len(error.evidence["observed_replies"]),
                                     stderr=error.evidence["stderr"]))
                    continue
                r=x["r"];req=x["requests"]
                if anchor and len(req)>=first:
                    lhs=[v["reply"] for v in req[:first]]
                    rhs=[v["reply"] for v in anchor["requests"]]
                    if lhs!=rhs or [v["name"] for v in req[:first]]!=[v["name"] for v in anchor["requests"]]:
                        raise ValueError("budget changed prefix before first signed contribution")
                base=first if mode=="continuation" and first is not None else 0
                after=req[base:] if mode=="total" or first is not None else []
                post=sum(v["ops"] for v in after)
                positive={digest(v["name"]) for v in after if v["ops"] and v["complete"]}
                ref=set(anchor["r"]["facts"]) if mode=="continuation" and anchor else set()
                facts=set(r["facts"])
                row=dict(**self.condition,mode=mode,budget=cap,first=first,paid_total=len(req),
                         paid=len(after),shortfall=max(0,cap-len(after)),ops_total=r["ops"],
                         ops=post,distinct_positive_names=len(positive),covered_total=len(facts),
                         new_facts=len(facts-ref) if mode=="total" or anchor else None,
                         lost_facts=len(ref-facts),reference=r["reference"],coverage=r["coverage"],
                         ept=r["ept"],continuation_ept=(post/len(after) if mode=="continuation" and after else None),
                         eps=r["eps"],wall=r["wall"],graph=r["graph"],higher=r["stats"].get("higher_completed",0),
                         higher_selected=r["stats"].get("higher_selected",0),statuses=r["receipts"])
                if mode=="continuation" and anchor:
                    # Deliberately offline. Distinct reference effects may be shared by different names.
                    outcomes=defaultdict(set)
                    productive={v["owner"] for v in after if v["ops"] and v["complete"]}
                    for i,v in enumerate(after,base):
                        if v["owner"] in productive and v["ops"]:
                            before=self.effect(req[:i]); new=self.effect(req[:i+1])
                            gain=set(new["facts"])-set(before["facts"])
                            lost=set(before["facts"])-set(new["facts"])
                            outcomes[v["owner"]].update(("+",j) for j in gain)
                            outcomes[v["owner"]].update(("-",j) for j in lost)
                    exact=self.effect(req)
                    if (exact["graph"],exact["facts"],exact["ops"])!=(r["graph"],r["facts"],r["ops"]):
                        raise ValueError("offline named replay and independent native result disagree")
                    row["distinct_visible_effects"]=len({frozenset(effect) for effect in outcomes.values()
                                                         if any(tag=="+" for tag,_ in effect)})
                    row["unresolved_effects"]=sum(not any(tag=="+" for tag,_ in outcomes[o]) for o in productive)
                    row["productive_complete_instances"]=len(productive)
                rows.append(row)
        self.db.put("curve",digest(self.condition),rows)


def run(a):
    db=Database(output(a)/"native.sqlite")
    for case in os.getenv("EXPOSURE_CASES","sum-divisors").split():
        if case in HELD and not (output(a)/"split.json").exists():
            raise ValueError("missing prospective program split")
        for name in os.getenv("EXPOSURE_MODELS","random history local-s71-t100000").split():
            for seed in map(int,os.getenv("EXPOSURE_DRAWS","193 307").split()):
                for unique in map(int,os.getenv("EXPOSURE_UNIQUE","1").split()):
                    trial=Trials(a,db,case,name,seed,bool(unique))
                    if db.get("curve",digest(trial.condition)) is None:
                        start=perf_counter()
                        trial.run()
                        print(case,name,seed,unique,round(perf_counter()-start,2),flush=True)
                    if os.getenv("EXPOSURE_FULL") == "1":
                        try:
                            trial.trial(None)
                        except SourcePanic:
                            pass  # The failed full schedule is already in the native ledger.


if __name__=="__main__":
    torch.set_num_threads(1)
    with torch.no_grad():
        run(args())
