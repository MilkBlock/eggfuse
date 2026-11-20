"""Online entrypoint. No reference program, recorded matches or CPU fallback."""
import argparse,hashlib
from pathlib import Path
import sys
from catalog import read,validate_device_contracts
GPU=Path(__file__).resolve().parents[1];sys.path.insert(0,str(GPU))
from run import execute

def run(packet,reader,ports,catalog,checkpoint,out,completion=True):
    static=read(catalog);model=read(checkpoint)
    if hashlib.sha256(packet.read_bytes()).hexdigest()!=static['image_sha256']:
        raise ValueError('catalog from different program')
    if static['schema']!='eggfuse.leaf-catalog/v1' or model['schema']!='eggfuse.recurrent-leaf/v1':
        raise ValueError('unsupported neural action format')
    validate_device_contracts(packet.parent,static['entries'])
    rows,h,ranks,leaves=(model[k] for k in ('rows','hidden','ranks','leaves'))
    if (rows,h,ranks,leaves)!=(2,8,8,32) or len(static['entries'])!=leaves:
        raise ValueError('unsupported neural shape')
    size=h*h+3*h+32*h+rows*h+(leaves+1)*h+ranks*h+6*h+leaves+6+h+1
    if len(model['weights'])!=size:raise ValueError('wrong actor checkpoint size')
    return execute(packet,reader,ports,2048,2,out,neural=dict(catalog=static['entries'],weights=model['weights'],
        rows=rows,hidden=h,ranks=ranks,complete_residual=completion))
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('packet','reader','ports','catalog','checkpoint','out'):p.add_argument(k,type=Path)
    p.add_argument('--no-exact-completion',action='store_true')
    a=p.parse_args();run(a.packet,a.reader,a.ports,a.catalog,a.checkpoint,a.out,not a.no_exact_completion)
