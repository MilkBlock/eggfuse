"""Sample both resident binaries, including all native API and executor costs."""
import argparse
import json
from pathlib import Path
import subprocess
from time import perf_counter


def sample(args):
    args.out.mkdir(parents=True, exist_ok=False)
    root = args.out / 'root.json'
    root.write_text(json.dumps(dict(control='use', forbid_fallback=True, encoding='resident')))
    report = {}
    for case in args.cases:
        bundle = args.bundles / f'{case}-1703'
        req = json.loads((bundle / 'request.json').read_text())
        for k in ('single_config', 'merge_config'):
            req[k] = str(bundle / req[k])
        req.update(root_config=str(root), multi_mode='rowdeltapairguardstackseallearned', radius=0,
                   packed_lookup=True, baked_row_index=False, audit=False,
                   multi_weights=str(args.weights / f'{case}-1703-tied.json'),
                   baked_codes=str(args.weights / f'{case}-1703-tied.bin'))
        arms={'resident':(args.tuned,req),'vanilla':(args.vanilla,{})}
        if args.tuned_rows:
            checked=args.out/'checked.json'
            checked.write_text(json.dumps(dict(control='use',forbid_fallback=True,encoding='checked_slots')))
            arms['tuned']=(args.tuned_rows,dict(req,root_config=str(checked),
                            rows=dict(action=4,max_rows=1,workers=1,batch=True,verify=2)))
        for arm,(binary,request) in arms.items():
            key = case + '-' + arm
            params = [binary,bundle/'program.json']
            if arm!='vanilla':params.append(bundle/'plans.json')
            cmd = json.dumps(request) + '\n'
            with subprocess.Popen(params, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True) as child:
                def run():
                    start = perf_counter()
                    child.stdin.write(cmd)
                    child.stdin.flush()
                    raw = child.stdout.readline()
                    elapsed = (perf_counter()-start)*1000.
                    result = json.loads(raw)
                    if arm=='tuned':
                        assert result['single']['adaptive_rows']['stats']['emitted']>0
                        assert result['multi']['counts']['raw_tuples']>0
                    return result['ms'], elapsed, result['state_sha']
                warm = run()
                path = args.out / (key+'.sample')
                with subprocess.Popen(['/usr/bin/sample',str(child.pid),str(args.seconds),'1','-file',str(path)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL) as sampler:
                    timings = []
                    while sampler.poll() is None:
                        cost = run()
                        assert cost[2]==warm[2]
                        timings.append(cost[:2])
                    if sampler.returncode or not path.exists():
                        raise RuntimeError(f'sample failed: {key}')
                child.stdin.close()
                report[key]=dict(inference_and_roundtrip_ms=timings, state_sha=warm[2])
                print(key, len(timings), flush=True)
            (args.out/'timing.json').write_text(json.dumps(report, indent=1)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('tuned','vanilla','bundles','weights','out'):
        parser.add_argument(key,type=Path)
    parser.add_argument('--cases', nargs='+', default=['jacobi-1d','conjugate-gradient'])
    parser.add_argument('--tuned-rows',type=Path)
    parser.add_argument('--seconds',type=int,default=6)
    sample(parser.parse_args())
