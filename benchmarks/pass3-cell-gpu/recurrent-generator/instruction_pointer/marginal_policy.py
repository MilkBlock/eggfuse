"""Calibrate a frozen neural issuance score with single-decision full-rollout differences."""
import argparse
from collections import Counter
import json
from pathlib import Path
import shutil
import subprocess

import torch

from alternate_proofs import digest
from higher_cell import read
from layout_credit_report import verify
from receipt_value import ReceiptChoice
from ripsat_replay import unpack
from train_ripsat import layout_id


def splits(protocol_path):
    protocol = read(protocol_path)
    hashes, names = set(), set(protocol['development_only'])
    for name in ('train','validation','test'):
        partition = protocol[name]
        if (not partition or len(set(partition.values())) != len(partition) or
                hashes.intersection(partition.values()) or names.intersection(partition)):
            raise ValueError('empty or overlapping program partition')
        hashes.update(partition.values())
        names.update(partition)
    return protocol


def fit(data, base, baked, protocol_path, out):
    protocol = splits(protocol_path)
    policy = ReceiptChoice(base,baked)
    if policy.cut:
        raise ValueError('interventions require the uncalibrated logging policy')
    study = read(baked/'study.json')
    graphs = unpack(read(baked/'catalog.json'))
    samples, proofs = {}, {}
    setup = set()
    for name,tape in study['training'].items():
        path = data/(name+'.json')
        sample = read(path)
        m = sample['metadata']
        if (protocol['train'].get(name) != m['program_sha'] or m['program'] != name or m['actor'] != study['root_weights'] or m['tape'] != tape or
                m['policy'] != policy.checkpoint or m['catalog'] != study['catalog_sha']):
            raise ValueError('unexpected intervention provenance')
        setup.add((m['binary'],m['recovery'],m['seed'],m['draws']))
        rows = sample['rows']
        counts = Counter(r['stratum'] for r in rows)
        if (counts != {k:min(m['draws'],n) for k,n in m['populations'].items()} or
                len({r['token'] for r in rows}) != len(rows)):
            raise ValueError('incomplete sampled strata')
        population = sum(m['populations'].values())
        for r in rows:
            if (int(layout_id(graphs[r['layout']])[:8],16)%8 == 0 or
                    r['net_signed'] != len(r['added'])-len(r['lost']) or
                    set(r['added']).intersection(r['lost']) or
                    r['probability'] != counts[r['stratum']]/m['populations'][r['stratum']]):
                raise ValueError('invalid layout split, ordinal difference or inclusion probability')
            with torch.no_grad():
                r['outcomes'] = policy.outcomes(torch.tensor(r['context']), [r['layout']])[0].tolist()
            if sum(x*y for x,y in zip(r['outcomes'],policy.prices.tolist(),strict=True)) <= 0:
                raise ValueError('logged action outside the base support')
            r['population'] = population
        samples[name] = rows
        proofs[name] = digest(path)
    if len(setup) != 1:
        raise ValueError('incompatible rollout settings')
    if set(samples) != set(protocol['train']):
        raise ValueError('missing training program')
    rows = [r for program in samples.values() for r in program]
    device = 'mps'
    x = torch.tensor([r['outcomes']+[1.] for r in rows], device=device)
    y = torch.tensor([r['net_signed']+.25*r['saved_packets'] for r in rows], device=device)
    w = torch.tensor([1./(r['probability']*r['population']) for r in rows], device=device)
    w /= w.sum()
    scale = ((w[:,None]*x.square()).sum(0)).sqrt().clamp_min(.05)
    prior = torch.tensor([*policy.prices.tolist(),0.], device=device)
    delta = torch.nn.Parameter(torch.zeros(4,device=device))
    optimizer = torch.optim.Adam([delta], lr=.01)
    for _ in range(128):
        errors = x @ prior + (x/scale) @ delta - y
        cost = (w*errors.square()).sum() + delta.square().sum()
        optimizer.zero_grad()
        cost.backward()
        optimizer.step()
    adjustment = (delta.detach()/scale).cpu()
    for strength in protocol['strengths']:
        if strength == 0:
            continue
        info = read(base/'training.json')
        coeffs = prior.cpu()+strength*adjustment
        info.update(prices=coeffs[:3].tolist(), issuance_cut=-float(coeffs[3]), fork_data=proofs,
                    strength=strength, base_policy=policy.checkpoint, intervention_build=next(iter(setup))[0],
                    protocol=digest(protocol_path), episodes=len(rows), device='mps')
        folder = out/arm_name(strength)
        folder.mkdir(parents=True,exist_ok=True)
        for file in ('policy.pt','values.pt'):
            shutil.copyfile(base/file,folder/file)
        (folder/'training.json').write_text(json.dumps(info,indent=2)+'\n')


def arm_name(strength):
    return 'base' if strength == 0 else f'cal-{strength:g}'


def lock(protocol_path, corpus, evaluations, base, policies, output):
    protocol = splits(protocol_path)
    candidates, controls = {}, {}
    for strength in protocol['strengths']:
        arm = arm_name(strength)
        folder = base if strength == 0 else policies/arm
        meta = read(folder/'training.json')
        if strength and (meta['protocol'] != digest(protocol_path) or meta['strength'] != strength):
            raise ValueError('candidate does not match fixed protocol')
        sha = digest(folder/'training.json') if strength else meta['policy']
        by_program = {}
        for name,program_sha in protocol['validation'].items():
            report = read(evaluations/arm/(name+'.json'))
            if (digest(corpus/name/'program.json') != program_sha or report['program'] != name or
                    report['tape'] != digest(corpus/name/'tape.json') or report['policy'] != sha):
                raise ValueError('unexpected validation input or policy')
            settings = [report[k] for k in ('mode','binary','actor','reader','scorer','catalog','recovery',
                                               'omit','attach','seed','reference_commits')]
            if report['mode'] != 'native assist' or controls.setdefault(name,settings) != settings:
                raise ValueError('validation arms use different runtime settings')
            verify(report, read(corpus/name/'exact.json'))
            result = report['execution']
            by_program[name] = dict(signed=result['counts']['accepted'], required=report['reference_commits'],
                paid=result['issued'], ops=sum(result['ept']['signed_external']+result['ept']['signed_internal']),
                audit=digest(evaluations/arm/(name+'.json')))
        recalls = [r['signed']/r['required'] for r in by_program.values()]
        key = [min(recalls),sum(recalls)/len(recalls),
               sum(r['ops'] for r in by_program.values())/sum(r['paid'] for r in by_program.values()),-strength]
        candidates[arm] = dict(strength=strength, policy=sha, programs=by_program, ranking=key)
    winner = max(candidates,key=lambda k:candidates[k]['ranking'])
    result = dict(protocol=digest(protocol_path),selected=winner,policy=candidates[winner]['policy'],
                  candidates=candidates)
    if output.exists() and read(output) != result:
        raise ValueError('existing validation lock differs')
    output.write_text(json.dumps(result,indent=2)+'\n')


def test_locked(protocol_path, lockfile, corpus, donor, binary, weights, baked, base, policies, recovery, out):
    from layout_credit import CreditIssuer, load_policy, rollout
    from live_ripsat import evaluate
    from prefix_policy import Policy
    from prefix_recovery import Recovery

    protocol = splits(protocol_path)
    selection = read(lockfile)
    if selection['protocol'] != digest(protocol_path):
        raise ValueError('test protocol differs from the validation lock')
    arm = selection['selected']
    model = load_policy(base if arm=='base' else policies/arm,baked)
    if model.checkpoint != selection['policy']:
        raise ValueError('test policy differs from validation winner')
    pre = Policy(32,recovery=Recovery(recovery,weights))
    def issuer(actor, source, target, library, native):
        return CreditIssuer(actor,source,target,library,omit=True,explore=False,seed=1703,policy=model,attach=True)
    for name, expected in protocol['test'].items():
        folder = corpus/name
        program = folder/'program.json'
        if digest(program) != expected:
            raise ValueError('test program identity changed')
        for role,filename,last in [('capture','capture.json',[]),('reference','exact.json',['--ept'])]:
            tape = folder/'tape.json' if role=='capture' else '-'
            with (folder/filename).open('w') as stream:
                subprocess.run([binary,role,program,tape,'audit',*last],stdout=stream,check=True)
        rollout(corpus,donor,binary,weights,baked,out/'assist',name,1703,True,False,
                policy=model,attach=True,run_recall=True,prefix=pre)
        assist = read(out/'assist'/(name+'.json'))
        verify(assist,read(folder/'exact.json'))
        exclusive = out/'exclusive'
        exclusive.mkdir(parents=True,exist_ok=True)
        evaluate(corpus,read(donor/'program.json'),binary,weights,baked,name,exclusive/(name+'.json'),
                 False,True,exclusive=True,issuer_factory=issuer,prefix=pre)
        report = read(exclusive/(name+'.json'))
        if report['independent_search_calls'] != 0:
            raise ValueError('exclusive test invoked residual search')
        report.update(lock=digest(lockfile),policy=model.checkpoint,recovery=pre.recovery.checkpoint)
        (exclusive/(name+'.json')).write_text(json.dumps(report,indent=2)+'\n')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='cmd',required=True)
    for cmd,keys in [('fit',('data','base','baked','protocol','out')),
                     ('lock',('protocol','corpus','evaluations','base','policies','out')),
                     ('test',('protocol','lockfile','corpus','donor','binary','weights','baked','base','policies','recovery','out'))]:
        parser = sub.add_parser(cmd)
        for k in keys:
            parser.add_argument(k,type=Path)
    a = p.parse_args()
    torch.set_num_threads(1)
    if a.cmd=='fit':
        fit(a.data,a.base,a.baked,a.protocol,a.out)
    elif a.cmd=='test':
        test_locked(a.protocol,a.lockfile,a.corpus,a.donor,a.binary,a.weights,a.baked,a.base,a.policies,a.recovery,a.out)
    else:
        lock(a.protocol,a.corpus,a.evaluations,a.base,a.policies,a.out)
