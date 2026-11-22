"""Exercise extreme signed operands through compiled source and the named receiver."""
import argparse
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from compare import compare


def check(args,root):
    values=[-(1<<63),-(1<<63)+1,-17,-16,-1,0,15,16,17,(1<<63)-2,(1<<63)-1]
    ops=("<","<=",">",">=","!=")
    constructors=" ".join(f"(Hit{i} E E)" for i in range(len(ops)))
    source=[f"(datatype E (L i64 i64) (R i64 i64) {constructors})","(ruleset check)"]
    for i,op in enumerate(ops):
        source.append(f"(rule ((= l (L key x)) (= r (R key y)) ({op} x y)) ((Hit{i} l r)) :ruleset check)")
    for i,x in enumerate(values):
        for j,y in enumerate(values):
            key=i*len(values)+j
            source.extend((f"(L {key} {x})",f"(R {key} {y})"))
    source.append("(run-schedule (run check))")
    egg=root/"edges.egg"
    egg.write_text("\n".join(source))
    bundle=root/"compiled"
    subprocess.run([args.compiler,"compile","--source",egg,"--output",bundle],check=True,capture_output=True)
    program=bundle/"program.json"
    plans=root/"plans.json"
    plans.write_text("[]")
    gold=json.loads(subprocess.check_output([args.reference,program,plans],input=b'{"baseline":true,"audit":true}\n'))
    model=json.loads(Path(__file__).with_name("scalar-model.json").read_bytes())
    model.update(wide_scalar=True,port_distinct=True)
    path=root/"wide.json"
    path.write_text(json.dumps(model))
    data=json.loads(subprocess.check_output([args.native,program,path]))
    checks=compare(data,gold)["checks"]
    # For each pair exactly two directional predicates pass, plus != on distinct inputs.
    count=2*len(values)**2+len(values)*(len(values)-1)
    if not all(checks[k] for k in ("rhs","state_sha","schedule","writes","mutation_trace")):
        raise ValueError(checks)
    if data["failure"] or data["issuer"]["issued"]!=count or data["accepted"]!=count or data["rejected"]:
        raise ValueError((count,data["issuer"],data["rejected"]))
    model["scalars"]["<"]=[0.,0.,1.]
    path.write_text(json.dumps(model))
    bad=subprocess.run([args.native,program,path],capture_output=True,text=True)
    if not bad.returncode or "uncertified scalar readout" not in bad.stderr:
        raise ValueError("invalid checkpoint accepted")
    print(f"{count} accepted; corrupt checkpoint rejected")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ("compiler","native","reference"):
        p.add_argument(arg,type=Path)
    with TemporaryDirectory() as folder:
        check(p.parse_args(),Path(folder))
