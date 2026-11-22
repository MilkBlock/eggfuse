"""Online entrypoint. No reference program, recorded matches or CPU fallback."""
import argparse,hashlib
from pathlib import Path
import sys
from catalog import read,validate_device_contracts,validate_join_ports
GPU=Path(__file__).resolve().parents[1];sys.path.insert(0,str(GPU))
from run import execute

def run(packet,reader,ports,catalog,checkpoint,out,completion=True,bootstrap_only=False):
    static=read(catalog);model=read(checkpoint)
    if hashlib.sha256(packet.read_bytes()).hexdigest()!=static['image_sha256']:
        raise ValueError('catalog from different program')
    chain=model['schema']=='eggfuse.compound-chain/v1'
    compound=chain or model['schema']=='eggfuse.compound-pair/v1'
    if compound:
        entries=static['entries']
        if static['schema']!='eggfuse.compound-catalog/v1' or static['joins']!=model['joins']:
            raise ValueError('policy/catalog joins differ')
        extra=dict(named_boundary=model.get('named_boundary',False))
        if chain:
            for field in ('tails','wires'):
                if field not in static or static[field]!=model[field]:
                    raise ValueError('policy/catalog continuation differs')
                extra[field]=static[field]
        validate_device_contracts(packet.parent,entries)
        validate_join_ports(packet.parent,entries,static['joins'])
        if len(entries)!=32 or len(model['roots'])!=783:raise ValueError('invalid root policy shape')
        return execute(packet,reader,ports,2048,2,out,neural=dict(catalog=entries,weights=model['roots'],rows=2,
            hidden=8,ranks=8,waves=2,complete_residual=completion,bootstrap_only=bootstrap_only,
            compound=dict(joins=static['joins'],child=model['child'],batch=True,**extra)))
    receipt_head = model['schema']=='eggfuse.recurrent-receipts/v1'
    if static['schema']!='eggfuse.leaf-catalog/v1' or not (receipt_head or model['schema']=='eggfuse.recurrent-leaf/v1'):
        raise ValueError('unsupported neural action format')
    validate_device_contracts(packet.parent,static['entries'])
    rows,h,ranks,leaves=(model[k] for k in ('rows','hidden','ranks','leaves'))
    if (rows,h,ranks,leaves)!=(2,8,8,32) or len(static['entries'])!=leaves:
        raise ValueError('unsupported neural shape')
    size=h*h+3*h+32*h+rows*h+(leaves+1)*h+ranks*h+6*h+leaves+6+h+1
    extra = {}
    if receipt_head:
        if model['waves'] != 2 or model['feedback'] not in (0,1,2):
            raise ValueError('unsupported receipt policy')
        size += 8*h+8
        extra = dict(waves=2, feedback=model['feedback'], receipt_head=True)
    if len(model['weights'])!=size:raise ValueError('wrong actor checkpoint size')
    return execute(packet,reader,ports,2048,2,out,neural=dict(catalog=static['entries'],weights=model['weights'],
        rows=rows,hidden=h,ranks=ranks,complete_residual=completion,bootstrap_only=bootstrap_only,**extra))
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('packet','reader','ports','catalog','checkpoint','out'):p.add_argument(k,type=Path)
    group=p.add_mutually_exclusive_group()
    group.add_argument('--no-exact-completion',action='store_true')
    group.add_argument('--only-exact-empty-lhs',action='store_true')
    a=p.parse_args();run(a.packet,a.reader,a.ports,a.catalog,a.checkpoint,a.out,not (a.no_exact_completion or a.only_exact_empty_lhs),a.only_exact_empty_lhs)
