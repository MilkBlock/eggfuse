"""Native arithmetic validation and bounded GPU two-stage/joint comparison."""
import argparse
import copy
import hashlib
import json
import statistics
import subprocess
import tempfile
import time
from pathlib import Path
import mlx.core as mx
import numpy as np
from compiler import Affine, Unsupported
from continuation import Continuation


def oracle(binary, rule, inputs, cases):
    with tempfile.TemporaryDirectory() as d:
        request, output = Path(d)/'input.json', Path(d)/'output.json'
        request.write_text(json.dumps(dict(rule=rule, inputs=inputs, cases=cases)))
        subprocess.run([str(binary.resolve()), str(request), str(output)], check=True, timeout=1.)
        return json.loads(output.read_text())


def median(fn, repeats):
    for _ in range(5): fn()
    times = []
    for _ in range(repeats):
        start = time.perf_counter_ns(); fn()
        times.append((time.perf_counter_ns()-start)/1e6)
    return statistics.median(times)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--oracle', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--repeats', type=int, default=20)
    a = ap.parse_args()
    assert mx.metal.is_available()
    mx.set_default_device(mx.gpu)
    path = Path(__file__).with_name('continuation-cases.json')
    fixture = json.loads(path.read_text())
    p, c = fixture['rules']
    joined = Continuation(p, c, fixture['operation'], fixture['atom'], fixture['table'])
    plan = joined.plan
    pp = Affine(p, plan.inputs, plan.bounds)
    ci = [i for i, s in enumerate(c['slots']) if s['definition']=='query' and s['sort']['kind']=='i64']
    cp = Affine(c, ci, [2*(1<<20)]*len(ci))
    actual = [r['input_values'] for r in fixture['records']]
    assert all(plan.eligible(row) for row in actual)
    rng = np.random.default_rng(4242)
    synthetic = rng.integers(1, 1<<20, size=(2048, len(plan.inputs))).tolist()
    cases = actual + synthetic + [[1<<20]*len(plan.inputs),[-(1<<20)]*len(plan.inputs)]
    pr = oracle(a.oracle, p, plan.inputs, cases)
    consumers = []
    for inputs, outputs in zip(cases, pr):
        env = dict(zip(plan.inputs, inputs)); env.update({int(k): v for k, v in outputs.items()})
        consumers.append([env[joined.wiring[i]['slot']] for i in ci])
    cr = oracle(a.oracle, c, ci, consumers)
    # Actual successful bindings must agree with these scalar connections.
    for record, values in zip(fixture['records'], consumers):
        bound = {v['slot']:v['value'] for v in record['consumer']['values']}
        assert values == [bound[i]['value'] for i in ci]
        assert record['consumer_run'] > record['producer_run']
    w, b = mx.array(plan.coefficients), mx.array(plan.bias)
    wp, bp, wc, bc = map(mx.array, [pp.coefficients, pp.bias, cp.coefficients, cp.bias])
    joint = mx.compile(lambda x: x@w+b)
    producer = mx.compile(lambda x: x@wp+bp)
    consumer = mx.compile(lambda x: x@wc+bc)
    prepared = joint(mx.array(np.array(cases, np.float32)))
    mx.eval(prepared)
    host = np.array(prepared)
    for stage, expected in enumerate([pr, cr]):
        for slot, column in joined.stage_columns[stage].items():
            np.testing.assert_array_equal(host[:,column], np.array([row[str(slot)] for row in expected], np.float32))
    for slot in joined.stage_columns[1]:
        np.testing.assert_array_equal(np.array(joined.consumer_column(prepared, slot)), host[:,joined.stage_columns[1][slot]])

    rejected = []
    def must_reject(name, producer_rule=p, consumer_rule=c, table=fixture['table'], bound=1<<20):
        try: Continuation(producer_rule, consumer_rule, fixture['operation'], fixture['atom'], table, bound)
        except Unsupported: rejected.append(name)
        else: raise AssertionError(name)
    bad = copy.deepcopy(fixture['table']); bad['kind']='function'
    must_reject('mutable boundary', table=bad)
    bad = copy.deepcopy(c); bad['query'][0]['call']['table']='Other'
    must_reject('unrelated constructor', consumer_rule=bad)
    bad = copy.deepcopy(c); bad['slots'].append(dict(sort=dict(kind='i64'), definition='query'))
    must_reject('late scalar input', consumer_rule=bad)
    must_reject('unsafe accumulated range', bound=1<<24)
    assert not plan.eligible([1<<63]*len(plan.inputs))

    timings = []
    for repeat in (1, 64, 1024):
        integer_inputs = np.tile(np.array(actual, np.int64), (repeat, 1))
        def pack():
            assert np.all((integer_inputs >= -np.array(plan.bounds)) & (integer_inputs <= np.array(plan.bounds)))
            return mx.array(integer_inputs.astype(np.float32))
        def separate():
            x = pack(); y = producer(x); mx.eval(y)
            fields = []
            for slot in ci:
                source = joined.wiring[slot]['slot']
                fields.append(y[:,pp.output_columns[source]] if source in pp.output_columns else x[:,plan.inputs.index(source)])
            z = consumer(mx.stack(fields, axis=1)); mx.eval(z)
            return np.array(y), np.array(z)
        def fused():
            # Producer and later consumer access the same retained device batch.
            y = joint(pack()); mx.eval(y)
            return np.array(y)
        def cpu():
            assert np.all((integer_inputs >= -np.array(plan.bounds)) & (integer_inputs <= np.array(plan.bounds)))
            # Same three prepared outputs, no native engine dispatch/effects.
            av, bv, cv = integer_inputs.T
            return np.stack((bv+cv, av+1, bv+cv-1), axis=1)
        cpu_ms = median(cpu, a.repeats)
        separate_ms = median(separate, a.repeats)
        fused_ms = median(fused, a.repeats)
        yp, yc = separate(); y = fused()
        np.testing.assert_array_equal(y, cpu())
        for slot, col in joined.stage_columns[0].items(): np.testing.assert_array_equal(y[:,col], yp[:,pp.output_columns[slot]])
        for slot, col in joined.stage_columns[1].items(): np.testing.assert_array_equal(y[:,col], yc[:,cp.output_columns[slot]])
        timings.append(dict(rows=len(integer_inputs), repeated_real_rows=repeat, separate_ms=separate_ms, joint_ms=fused_ms, cpu_numpy_ms=cpu_ms,
                            speedup=separate_ms/fused_ms))
    result = dict(scope='Standalone GPU scalar preparation replay, not integrated runtime takeover or whole-engine speedup',
        fixture_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), oracle_sha256=hashlib.sha256(a.oracle.read_bytes()).hexdigest(),
        actual_next_run_links=len(actual), synthetic_cases=len(cases)-len(actual), exact_scalar_results=len(cases)*3,
        input_slots=plan.inputs, coefficients=plan.coefficients.tolist(), bias=plan.bias.tolist(),
        stage_columns=joined.stage_columns, consumer_input_columns=joined.consumer_input_columns,
        certificates=plan.certificates, rejected=rejected, obligations=joined.obligations,
        before=dict(gpu_stage_submissions=2, consumer_input_assemblies=1, retained_output_columns=3),
        after=dict(gpu_stage_submissions=1, consumer_input_assemblies=0, retained_output_columns=3),
        engine_operations_removed=0, coefficient_bytes=plan.coefficients.nbytes+plan.bias.nbytes, repeats=a.repeats, timings=timings,
        timing_scope='Warm host requests: bound check, f32 packing, GPU evaluation and output reads; no actual Run, slot extraction, matching, publication, lifetime maintenance or consumer delay. Larger batches repeat 12 rows.')
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__': main()
