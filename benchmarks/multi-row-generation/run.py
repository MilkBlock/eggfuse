"""Train frozen multi-row generators; retain every variant, seed and failed graph."""
import argparse,json,hashlib,time,statistics,platform,sys
from pathlib import Path
import numpy as np
import mlx.core as mx
import mlx.nn as nn
import mlx.optimizers as optim
from task import generate,fingerprints,audit,KEYS,VALUES
from network import Generator,loss


def decoded(logits):
    out=[];start=0
    for width in (KEYS,KEYS,VALUES,VALUES):out.append(logits[...,start:start+width].argmax(-1));start+=width
    return np.stack(out,-1)


def arguments(data,indices=None):
    x=lambda k:mx.array(data[k] if indices is None else data[k][indices])
    return [x('x_a'),x('x_b')]+[mx.array(data[k]) for k in ('coords_a','coords_b','coords_pair')]


def as_host(result):
    mx.eval(result);return {k:np.array(v) for k,v in result.items()}


def forward_panel(model,data,erase=False):
    f=mx.compile(lambda a,b,pa,pb,pp:model.forward(a,b,pa,pb,pp,erase))
    pieces=[]
    for start in range(0,len(data['a']),64):pieces.append(as_host(f(*arguments(data,np.arange(start,min(start+64,len(data['a'])))))))
    return {k:np.concatenate([r[k] for r in pieces],axis=1) for k in pieces[0]}


def main():
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);p.add_argument('--mode',choices=['joint','independent'],required=True)
    p.add_argument('--train-family',choices=['involution','short_cycles'],default='involution');p.add_argument('--seed',type=int,required=True);p.add_argument('--steps',type=int,default=6000);a=p.parse_args()
    if not mx.metal.is_available():raise RuntimeError('Metal required; no CPU inference fallback')
    mx.set_default_device(mx.gpu);mx.random.seed(a.seed);a.output.mkdir(parents=True,exist_ok=True)
    train=[generate(r,l,1024,1200+i,a.train_family) for i,(r,l) in enumerate([(2,3),(3,2),(2,4),(4,2)])]
    tests=dict(seen=generate(2,4,256,9400),long_cycle=generate(2,4,256,9401,'long_cycle'),
        larger=generate(3,4,256,9402,'long_cycle'),more_rows=generate(8,2,256,9403,'long_cycle'),
        arbitrary=generate(4,4,256,9404,'arbitrary'))
    if a.train_family=='short_cycles':
        tests['final_fanin_rows']=generate(8,2,256,19403,'functional')
        tests['final_fanin_layout']=generate(3,4,256,19404,'functional')
    seen=set(v for d in train for v in fingerprints(d));split={}
    for name,d in tests.items():
        overlap=len(seen&set(fingerprints(d)));assert overlap==0
        split[name]=dict(rows=d['rows'],length=d['length'],graphs=len(d['a']),exact_input_overlap=overlap,
                         cycle_shapes=sorted(set(d['cycle_keys'])),input_sha256=hashlib.sha256(d['a'].tobytes()+d['b'].tobytes()).hexdigest())
    protocol=dict(train_family=a.train_family,mode=a.mode,seed=a.seed,steps=a.steps,train_graphs=sum(len(d['a']) for d in train),batch=64,learning_rate=.001,
        split=split,checkpoint_policy='fixed final step; heldouts evaluated only after fitting',
        source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path(__file__).parent.glob('*.py'))})
    (a.output/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
    model=Generator(a.mode);optimizer=optim.Adam(learning_rate=.001);grad=nn.value_and_grad(model,loss)
    rng=np.random.default_rng(a.seed);history=[];started=time.perf_counter()
    for step in range(a.steps):
        data=train[step%len(train)];ix=rng.integers(len(data['a']),size=64)
        value,g=grad(model,*arguments(data,ix),mx.array(data['targets'][:,ix]),mx.array(data['fields'][:,ix]))
        optimizer.update(model,g);mx.eval(value,model.parameters(),optimizer.state)
        if step%500==0 or step+1==a.steps:
            v=dict(step=step+1,loss=float(value),seconds=time.perf_counter()-started);history.append(v);print(json.dumps(v),flush=True)
    model.save_weights(str(a.output/'model.safetensors'))
    panels=dict(train_replay=train[2],**tests)
    predictions={name:forward_panel(model,d) for name,d in panels.items()}
    erased=forward_panel(model,tests['long_cycle'],True)
    probe=arguments(tests['seen'],np.arange(8));device=model.forward(*probe)
    _,second,_=model.emit(model.prepare(device['latent'][0],device['latent'][0],probe[-1],probe[-1],1));mx.eval(device,second)
    lineage=dict(second_step_consumes_generated_latent=bool(np.array_equal(second,device['latent'][1])),
                 original_inputs_available_to_second_step=False,teacher_latents=False)
    # Synchronized same-graph forward timing. This serialization is NOT AR.
    timing={};last_semantics={}
    d=tests['more_rows'];online=arguments(d,[0]);mx.eval(online)
    functions={'parallel':mx.compile(model.forward),'serial_same_queries':mx.compile(model.serial_same_queries)}
    for f in functions.values():
        for _ in range(4):mx.eval(f(*online))
    samples={k:[] for k in functions};last={}
    for rep in range(20):
        online=arguments(d,[rep]);mx.eval(online)
        order=list(functions) if rep%2==0 else list(reversed(functions))
        for name in order:
            start=time.perf_counter();last[name]=functions[name](*online);mx.eval(last[name]);samples[name].append((time.perf_counter()-start)*1000)
    for name,values in samples.items():timing[name]=dict(median_ms=statistics.median(values),samples_ms=values)
    timing['decoded_serial_equal']=bool(np.array_equal(decoded(np.array(last['parallel']['field_logits'])),decoded(np.array(last['serial_same_queries']['field_logits']))))
    # Independent CPU audits begin only after NN generation and controls finish.
    reports={};weight=np.array(model.decoder.weight).astype(np.float64);bias=np.array(model.decoder.bias).astype(np.float64)
    for name,d in panels.items():
        pred=predictions[name];fields=decoded(pred['field_logits'])
        report=audit(d,pred['pointers'],fields,pred['addresses'])
        cpu=decoded(pred['latent'].astype(np.float64)@weight.T+bias)
        report['cpu_decoder_agrees']=bool(np.array_equal(cpu,fields));reports[name]=report
        print(json.dumps(dict(panel=name,passed=report['whole_graph_passed'],graphs=report['graphs'],pointer=report['exact_pointer_count'],values=report['decoded_value_count'])),flush=True)
        np.savez_compressed(a.output/f'{name}.npz',a=d['a'],b=d['b'],coords_a=d['coords_a'],coords_b=d['coords_b'],coords_pair=d['coords_pair'],
                            decoder_weight=weight,decoder_bias=bias,**pred)
    erased_report=audit(tests['long_cycle'],erased['pointers'],decoded(erased['field_logits']),erased['addresses'])
    record=dict(status='pass' if all(r['whole_graph_passed']==r['graphs'] and r['cpu_decoder_agrees'] for r in reports.values()) else 'difference',
        protocol=protocol,panels=reports,erased_first_latent=erased_report,lineage=lineage,timing=timing,training=history,
        position_scale=dict(query=float(model.query_mix.position_scale),pointer=float(model.pointer.position_scale)),
        model_sha256=hashlib.sha256((a.output/'model.safetensors').read_bytes()).hexdigest(),cpu_corrections=0,
        scope='synthetic same-graph neural relational Cell generation, two stages, fixed anchor output layout',
        environment=dict(platform=platform.platform(),device=str(mx.default_device())),
        limitations=['no free row allocation or variable match multiplicity','no union/ownership conflict resolution or eggcc execution',
                     'fixed categorical key vocabulary, no arbitrary identity claim','query serialization is not an autoregressive baseline',
                     'whole-goal feasibility and end-to-end practical speed remain unproved'])
    (a.output/'result.json').write_text(json.dumps(record,indent=2)+'\n')
    if record['status']!='pass':sys.exit(1)

if __name__=='__main__':main()
