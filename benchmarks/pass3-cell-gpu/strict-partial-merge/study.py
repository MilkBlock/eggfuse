"""Same-binary factorial of independent strict root variants, signed releases and merge returns."""
import argparse,hashlib,json
from pathlib import Path
from runpy import run_path
from collections import Counter,defaultdict
from time import perf_counter
from statistics import median
HERE=Path(__file__).resolve().parent
merge=run_path(str(HERE.parent/'strict-merge-return/study.py'));partial=run_path(str(HERE.parent/'strict-partial-named-ports/study.py'))
src=merge['src'];opts={'leaf':(0,0),'partial2':(2,0),'merge':(0,1),'both':(2,1)}
fixed=('runs','rhs_count','state_sha','digests','root_commits_sha','root_fresh_sha','unions_sha','events_sha','birth_sha','export_original_sha','coalesced_sha','owned_births','effective_births')


def settings(req,depth,child,*,audit=False,stale=False):
    base=merge['filtered'](req,{'depth':depth,'partial':bool(depth),'record_links':audit,'stale_versions':stale})
    return dict(base,strict_merge=child,audit=audit,birth_ledger=audit)


def wire_ledger(rows,compiled,root,strict,depth):
    counts=Counter();stats_by_rule=defaultdict(Counter);tagged=set();ranges=[];proven={};examples={}
    templates={t['rule']:i for i,t in enumerate(compiled['templates'])}
    for single,rid,epoch,first,n,h,bitmap in rows:
        assert len(h)==8 and n>0
        raw=int.from_bytes(bytes(h),'little')
        low=raw&0xffffffff;spine=(raw>>32)&0x7fffffff;flag=raw>>63
        assert templates[rid]==low and spine in (0,rid+1) and flag==int(bitmap is not None)
        assert not single or not flag
        if not depth: assert spine==0
        if bitmap is not None:
            assert len(bitmap)==(n+7)//8
            if n%8:assert not bitmap[-1]>>(n%8)
        ranges.append((first,first+n))
        for ix in range(n):
            selected=bitmap is not None and bitmap[ix//8]&(1<<(ix%8))!=0
            serial=first+ix
            category=('both' if spine else 'merge') if selected else ('spine' if spine else 'none')
            if category not in examples:
                examples[category]={'original_header_le':h,'rid':rid,'template':low,'spine_program':spine,'epoch':epoch,'first_serial':first,'lane':ix,
                                    'merge_bitmap_byte':None if bitmap is None else bitmap[ix//8]}
            counts[category]+=1;stats_by_rule[rid][category]+=1
            if selected:tagged.add(serial)
            if serial in root:
                assert (root[serial][3],root[serial][4],root[serial][5])==(rid,low,epoch)
                proven[serial]=category
    assert len(tagged)==strict['tagged'] and sorted(ranges)==sorted(set(ranges))
    assert all(b[0]>=a[1] for a,b in zip(sorted(ranges),sorted(ranges)[1:]))
    assert len(tagged&root.keys())==strict['activated']
    return {'counts':counts,'commits':dict(Counter(proven.values())),'bytes_sha':merge['h'](rows),
            'examples':examples,'pages':len(rows),'source_tags_by_rule':dict(stats_by_rule),'bitmaps_bytes':sum(len(r[-1]) for r in rows if r[-1] is not None)},tagged,proven


def capture(v,gold,compiled,depth):
    q,children,raw,visible,root_by_ord=merge['read_ledger'](v,gold)
    roots={row[2]:row for row in root_by_ord.values()}
    signed=v['strict_named'] or {};serials={j[0]:j[1:] for j in signed.get('links',[])};c=q['strict']
    receipts={'records':[],'arms':{}};partial['collect_audit'](v,'this',receipts,{})
    assert len(serials)==len(receipts['arms']['this'])
    wire,tags,proven=wire_ledger(v['strict_template_words'],compiled,roots,c,depth)
    assert wire['bitmaps_bytes']==c['tag_bytes'] and sum(wire['counts'].values())==sum(v['root_recipe']['emitted'])
    assert wire['counts'].get('spine',0)+wire['counts'].get('both',0)==signed.get('counts',{}).get('tagged',0)
    assert not tags.intersection(serials)
    paid={row['allocated']<<32 for row in children.values() if row['allocated'] is not None};inner=set()
    for e in v['strict_merge']['events']:
        assert e[1] in tags
        if e[-1]:
            f=merge['addr'](e[-2]);assert f not in inner;inner.add(f)
    assert not (paid&inner) and (paid|inner)<=raw.keys()
    per=defaultdict(Counter)
    for f,(epoch,t,serial,flags) in raw.items():
        kind='paid_child' if f in paid else ('merge_internal' if f in inner else ('other_dynamic' if flags&2 else 'typed'))
        scope='cross_run' if serial in serials else 'external_root'
        k=scope+'/'+kind;per[k]['new']+=1;per[k]['visible']+=int(f in visible)
    assert sum(a['new'] for a in per.values())==q['owned_births'] and sum(a['visible'] for a in per.values())==q['effective_births']
    q.update(wire=wire,origin_partition=per,signed_sha=merge['h'](signed.get('signed_commits',[])),
             links=len(serials),link_depth=dict(Counter(v[1] for v in serials.values())),strict_counts=signed.get('counts',{}),
             partition=signed.get('partition',{}),merge_under_cross_run_root=sum(1 for e in v['strict_merge']['events'] if e[1] in serials),
             merges_on_dual_tagged_roots=sum(proven.get(e[1])=='both' for e in v['strict_merge']['events']))
    return q,children,raw,visible,root_by_ord


def main(a):
    a.out.mkdir(parents=True,exist_ok=True);result={}
    for case in a.cases:
        p,plan,req=src.config(a,case);compiled=json.loads(p.read_bytes())
        with src.base.session(a.exp/'compact-vanilla-20261121/vanilla-audit',p) as oracle:gold=oracle({'audit':True})
        rows={};leaf_children={};fault={}
        with src.base.session(a.native,p,plan) as run:
            for name,(depth,cm) in opts.items():
                v=run(settings(req,depth,cm,audit=True));assert 'source_error' not in v,(case,name,v.get('source_error'))
                q,ch,b,ends,roots=capture(v,gold,compiled,depth);rows[name]=q
                if not cm:leaf_children[depth]=ch
                else:q['verified_internal']=merge['verify_internal'](v,leaf_children[depth],ch,b,ends,roots)
                for k in fixed: assert q[k]==rows['leaf'][k],(case,name,k)
                print(case,name,q['emitted_roots'],q['selected_children'],q['packets'],q['fept'],q['wire']['counts'],flush=True);del v
            for n,m in [('merge_bit',1),('spine_bit',2)]:
                f=run(dict(settings(req,2,1),strict_wire_fault=m))
                assert f.get('source_error') and f['runs']<gold['runs'],(case,n)
                assert ('strict merge tag/payload conflict' in f['source_error'] if m==1 else 'strict variant' in f['source_error'])
                fault[n]=[f['runs'],f['source_error']]
            for n,m in [('old_ref',2),('old_version',3)]:
                f=run(settings(req,2,m));assert 'strict merge old reference differs' in f.get('source_error','') and f['runs']<gold['runs']
                fault[n]=[f['runs'],f['source_error']]
            sf=run(settings(req,2,1,audit=True,stale=True));assert 'source_error' not in sf,sf.get('source_error')
            st,sc,b,en,ro=capture(sf,gold,compiled,2)
            assert all(st[k]==rows['leaf'][k] for k in fixed) and st['partition']['stale_refs']>0
            fault['stale_partial_fallback']={k:st[k] for k in ('state_sha','runs','packets','selected_children','emitted_roots','links','strict','partition')}
            names=list(rows)
            for i in range(a.repeats+1):
                seq=names[i%len(names):]+names[:i%len(names)]
                for name in seq if i%2 else reversed(seq):
                    t=perf_counter();v=run(settings(req,*opts[name]));elapsed=1000*(perf_counter()-t)
                    assert v['runs']==gold['runs'] and v['state_sha']==gold['state_sha'] and v['root_recipe']['emitted']==rows[name]['emitted_roots']
                    assert v['strict_merge']['counts']==rows[name]['strict'] and v['merge_child']['counts'][1]==rows[name]['selected_children']
                    if i: rows[name]['ms'].append(v['ms']);rows[name]['wall_ms'].append(elapsed)
            for q in rows.values():q.update(median_ms=median(q['ms']),median_wall_ms=median(q['wall_ms']))
        result[case]={'arms':rows,'faults':fault};(a.out/'results.json').write_text(json.dumps(result,indent=1)+'\n')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for n in ('exp','native','out'):parser.add_argument(n,type=Path)
    parser.add_argument('--cases',nargs='+',default=['sum-bits','3mm']);parser.add_argument('--repeats',type=int,default=4)
    a=parser.parse_args();a.seed=1703;a.cap=8192;main(a)
