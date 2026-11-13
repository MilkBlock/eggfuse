"""Lower the entire recipe schedule and audit coverage against actual execution.

This is the full-program control/input contract, not GPU rule execution. CPU
change flags are used only to verify the lowered control against the trace.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


def lower(control, sets):
    code = []
    registers = 0

    def emit(node):
        nonlocal registers
        if set(node) == {'run'}:
            if node['run'] not in sets:
                raise ValueError('unknown ruleset: '+node['run'])
            code.append(dict(op='run', ruleset=node['run']))
        elif set(node) == {'sequence'}:
            for child in node['sequence']:
                emit(child)
        elif set(node) == {'saturate'}:
            slot = registers
            registers += 1
            start = len(code)
            code.append(dict(op='save_epoch', slot=slot))
            emit(node['saturate'])
            code.append(dict(op='repeat_if_changed', slot=slot, target=start))
        elif set(node) == {'repeat', 'body'}:
            count = node['repeat']
            if not isinstance(count, int) or count < 0:
                raise ValueError('invalid repeat count')
            if count:
                slot = registers
                registers += 2
                code.append(dict(op='counter', slot=slot, count=count))
                start = len(code)
                code.append(dict(op='save_epoch', slot=slot+1))
                emit(node['body'])
                code.append(dict(op='decrement_jump', slot=slot, epoch_slot=slot+1, target=start))
        else:
            raise ValueError('unsupported control must not be silently dropped: '+str(node))

    for node in control:
        emit(node)
    return code, registers


def replay(code, registers, steps):
    state = [0]*registers
    pc = epoch = consumed = instructions = 0
    while pc < len(code):
        instructions += 1
        if instructions > 10_000_000:
            raise ValueError('control did not terminate within audit budget')
        op = code[pc]
        if op['op'] == 'run':
            if consumed == len(steps) or steps[consumed]['ruleset'] != op['ruleset']:
                raise ValueError(f'Run mismatch at {consumed}: {op}')
            epoch += int(steps[consumed]['changed'])
            consumed += 1
        elif op['op'] == 'save_epoch':
            state[op['slot']] = epoch
        elif op['op'] == 'repeat_if_changed':
            if state[op['slot']] != epoch:
                pc = op['target']
                continue
        elif op['op'] == 'counter':
            state[op['slot']] = op['count']
        elif op['op'] == 'decrement_jump':
            state[op['slot']] -= 1
            if state[op['slot']] and state[op['epoch_slot']] != epoch:
                pc = op['target']
                continue
        pc += 1
    if consumed != len(steps):
        raise ValueError('trace has unconsumed Runs')
    return instructions


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('trace', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    trace = json.loads(args.trace.read_text())
    if not trace.get('all_slots') or not trace.get('run_control_counts_equal'):
        raise ValueError('requires all-slot trace with original Run controls verified')
    recipe = trace['recipe']
    sets = {s['name']:s['rule_ids'] for s in recipe['rulesets']}
    code, registers = lower(recipe['control'], sets)
    instruction_count = replay(code, registers, trace['steps'])
    bindings = Counter()
    slots = Counter()
    by_run = {r['ordinal']:r['audit']['bindings'] for r in trace['runs']}
    if len(by_run) != len(trace['runs']):
        raise ValueError('duplicate Run ordinals')
    for step in trace['steps']:
        rows = by_run.get(step['ordinal'], [])
        if len(rows) != step['executed_bindings']:
            raise ValueError('missing finalized Cell bindings')
        for row in rows:
            rid = row['rule']
            if rid not in sets[step['ruleset']]:
                raise ValueError('binding belongs to another ruleset')
            bindings[rid] += 1
            slots[rid] += len(row['values'])
    rule_plans = []
    for rid, rule in enumerate(recipe['rules']):
        # Retain the authoritative operations and typed layout, including all
        # queries, effects and source-rule identities. No SubTuple selection.
        rule_plans.append(dict(rule=rid, definition=rule,
            finalized_bindings=bindings[rid], captured_slot_values=slots[rid],
            subsume_excluded_from_gpu=any(e['kind']=='subsume' for e in rule['effects']),
            current_executor='cpu', gpu_completed_bindings=0))
    set_report = []
    for name, ids in sets.items():
        executions = [s for s in trace['steps'] if s['ruleset']==name]
        set_report.append(dict(ruleset=name, rules=len(ids), runs=len(executions),
            changed_runs=sum(s['changed'] for s in executions),
            finalized_bindings=sum(bindings[r] for r in ids),
            effect_kinds=dict(Counter(e['kind'] for r in ids for e in recipe['rules'][r]['effects'])),
            gpu_completed_bindings=0))
    summary = dict(scope='Full eggcc control lowering and typed input capture; CPU reference, not GPU takeover',
        trace_sha256=hashlib.sha256(args.trace.read_bytes()).hexdigest(),
        program_sha256=trace['program_sha256'], rules=len(rule_plans), rulesets=len(sets),
        runs=len(trace['steps']), finalized_bindings=sum(bindings.values()),
        captured_slot_values=sum(slots.values()), active_rules=len(bindings),
        control_instructions=len(code), control_registers=registers,
        replay_instructions=instruction_count, control_replay_exact=True,
        strict_reference_equal=trace['strict_audit_reference_equal'],
        gpu_completed_bindings=0, per_ruleset=set_report)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output/'plan.json').write_text(json.dumps(dict(code=code, registers=registers,
        rules=rule_plans, rulesets=sets, tables=recipe['tables']), indent=2)+'\n')
    (args.output/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k!='per_ruleset'}, indent=2))


if __name__ == '__main__':
    main()
