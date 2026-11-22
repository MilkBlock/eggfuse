"""Paired native paid-packet and surviving-constructor audit on the same inputs."""
import argparse
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from compare import compare

HERE=Path(__file__).resolve().parent
BUNDLES={"sum-bits":"joint-native-full-bundle-sum-bits","dot-product":"joint-native-full-bundle-dot-product",
         "3mm":"extra-pass3-transfer-v1/3mm-1703","deriche":"extra-pass3-transfer-v1/deriche-1703",
         **{s:f"compact-holdouts-20261121-v1/{s}-1703" for s in ("jacobi-1d","conjugate-gradient")},
         **{s:f"repair-bake-families-20261120/{s}" for s in ("gemm-bias-relu","stable-argmax")}}


def study(args, tmp):
    report={}
    models = {"baseline": HERE/"model.json","scalar": HERE/"scalar-model.json"}
    if args.wide:
        scalar=json.loads(models["scalar"].read_bytes())
        for name,flags in (("digits",{"wide_scalar":True}),
                           ("digits_and_identity",{"wide_scalar":True,"port_distinct":True})):
            path=tmp/(name+".json")
            path.write_text(json.dumps(dict(scalar,**flags)))
            models[name]=path
    for case, bundle in BUNDLES.items():
        program=args.exp/bundle/"program.json"
        plans=args.exp/BUNDLES["sum-bits"]/"plans.json"
        ref=json.loads(subprocess.check_output([args.reference,program,plans],
                         input=b'{"baseline":true,"audit":true}\n'))
        arms={}
        for arm,model in models.items():
            data=json.loads(subprocess.check_output([args.native,program,model]))
            audit=compare(data,ref)
            if (audit["failure"] or audit["issuer"]["denied_budget"] or audit["issuer"]["abstained"] or
                not all(audit["checks"][k] for k in ("state_sha","schedule","rhs","writes","mutation_trace"))):
                raise ValueError((case,arm,audit))
            counts=audit["issuer"]
            arms[arm]=dict(visible=data["visible_births"],origins=data["visible_sha"],
                           primitive_rejects=data["primitive_rejects"],paid=counts["issued"], accepted=audit["accepted"], rejected=audit["rejected"],
                           suppressed=counts["scalar_suppressed"], named_reads=audit["named_reads"],
                           fept=data["visible_births"]/counts["issued"],checks=audit["checks"])
            del data
        a=arms["baseline"]
        for name,b in arms.items():
            saved=a["paid"]-b["paid"]
            if (a["origins"]!=b["origins"] or a["accepted"]!=b["accepted"] or
                saved!=sum(b["suppressed"].values()) or saved!=a["rejected"]-b["rejected"]):
                raise ValueError((case,name,"lost or unattributed outputs"))
        report[case]=arms
        args.out.write_text(json.dumps(report,indent=2)+"\n")
        print(case,a["visible"],a["paid"],b["paid"],b["rejected"],flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ("exp","native","reference","out"):
        p.add_argument(arg,type=Path)
    p.add_argument("--wide",action="store_true")
    with TemporaryDirectory() as tmp:
        study(p.parse_args(),Path(tmp))
