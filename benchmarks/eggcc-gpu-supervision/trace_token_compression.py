"""Layer diagnostics for two finite-domain states; model weights unchanged."""
import argparse,json,hashlib
from pathlib import Path
import numpy as np
import mlx.core as mx
from neural_ordered_relations import ordered_model
from train_neural_cell_chains import incoming_tokens


def main():
    p=argparse.ArgumentParser();p.add_argument('pair',type=Path);p.add_argument('weights',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--edge-residual',action='store_true');a=p.parse_args()
    data=dict(np.load(a.pair,allow_pickle=False));parent={k[2:]:mx.array(v) for k,v in data.items() if k.startswith('p_')};chain={k[2:]:mx.array(v) for k,v in data.items() if k.startswith('c_')}
    if len(chain['valid'])!=2:raise ValueError('exactly two states required')
    m=ordered_model(parent['x'].shape[-1],parent['relations'].shape[-1],True,edge_residual=a.edge_residual);m.load_weights(str(a.weights))
    _,generated=m(parent['x'],parent['edges'],parent['mask'],parent['request'],parent['relations'])
    source=incoming_tokens(m,chain,generated);edges=chain['edges'];mask=chain['mask'];request=chain['request'];layers={}
    def record(name,x):
        mx.eval(x);v=np.array(x);layers[name]=dict(max_difference=float(np.max(np.abs(v[0]-v[1]))),max_abs=float(np.max(np.abs(v))))
    record('source_tokens',source);record('edges',edges)
    h=m.source(source);q=m.request(request);record('source_projection',h)
    scores=(m.query(h)@mx.swapaxes(m.key(h),-1,-2))/(m.hidden**.5)+m.edge_score(edges)[...,0]
    weights=mx.softmax(mx.where(mask[:,None,:],scores,-1e9),axis=-1);record('attention_weights',weights)
    context=mx.sum(weights[...,None]*(m.value(h)[:,None,:,:]+m.edge_value(edges)),axis=2);record('context',context)
    h=m.norm(h+context);record('first_norm',h);h=m.norm(h+m.mix(h));record('mixed_norm',h)
    pool=mx.sum(h*m.pool_query(q)[:,None,:],axis=-1)/(m.hidden**.5)
    pooled_weights=mx.softmax(mx.where(mask,pool,-1e9),axis=-1)
    z=m.finish(mx.concatenate([mx.sum(pooled_weights[...,None]*h,axis=1),q],axis=1));record('pooled_hidden',z)
    raw=m.successor(z);record('pre_tanh',raw);token=mx.tanh(raw);record('post_tanh',token)
    token=token+m.token_relation(m.relation(chain['relations']));record('pooled_token',token)
    if a.edge_residual:
        valid=mask[:,:,None]&mask[:,None,:]
        residual=m.edge_residual(mx.where(valid[...,None],edges,0).reshape(len(edges),-1))
        record('edge_residual',residual);token=token+residual
    record('final_token',token)
    _,actual=m.transition(source,edges,mask,request,chain['relations']);mx.eval(actual)
    np.testing.assert_allclose(np.array(token),np.array(actual),atol=1e-6,rtol=1e-6)
    result=dict(scope='unchanged trained model layer diagnostic; not accuracy or execution acceptance',layers=layers,
                attention=np.array(weights).tolist(),pooling=np.array(pooled_weights).tolist(),mask=np.array(mask).tolist(),
                weights_sha256=hashlib.sha256(a.weights.read_bytes()).hexdigest(),pair_sha256=hashlib.sha256(a.pair.read_bytes()).hexdigest())
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))


if __name__=='__main__':main()
