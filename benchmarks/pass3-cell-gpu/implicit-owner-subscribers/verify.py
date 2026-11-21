"""Check exact logical reverse domains, physical accounting, deployment and released native allocations."""
from pathlib import Path
import hashlib,json,sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'pair-source-frontier'))
from evidence import checked


def verify(folder):
    manifest=json.loads((folder/'manifest.json').read_bytes())
    assert manifest['base']=='31bf7e41' and manifest['extensions'][-1]==folder.name
    assert all(hashlib.sha256((folder/k).read_bytes()).hexdigest()==v for k,v in manifest['sources'].items())
    fixed=checked(folder,('storage.json',),('sum-bits','3mm'))
    derived=checked(folder,('derived.json',),('sum-bits','3mm'))
    for timing,resource,required in ((fixed,'heap.json',{'off','small','empty','owner','inline','hybrid'}),
                                     (derived,'derived-heap.json',{'off','empty','diff','derived'})):
        heap=json.loads((folder/resource).read_bytes())
        assert set(heap)==set(timing)
        for case,arms in timing.items():
            assert set(arms)==required|{'vanilla'} and set(heap[case])==required
            baseline=arms['off']['directory'];control=arms['empty']['directory']['work']
            for kind in required:
                q=arms[kind]['directory'];work=q['work'];measured=heap[case][kind]
                assert q['logical_edges']==baseline['logical_edges']==q['tree_edges']+q['implicit_self']+q['inline_single']+q['forward_derived']
                assert q['repairs']==baseline['repairs'] and q['unions']==baseline['unions']
                assert q['maintenance']['stats']['live_reverse_edges']==q['logical_edges']
                assert q['maintenance']['stats']['peak_reverse_edges']==baseline['maintenance']['stats']['peak_reverse_edges']
                assert q['maintenance']['stats']['union_wake_visits']==baseline['maintenance']['stats']['union_wake_visits']
                if kind!='off':
                    assert work['domain_audits']>0
                    for f in ('audited_owner_absent','audited_owner_only','audited_owner_with_readers','audited_other_readers'):
                        assert work[f]==control[f]
                    assert work['audited_owner_known']==work['audited_owner_absent']+work['audited_owner_only']+work['audited_owner_with_readers']
                if kind in ('owner','hybrid'):
                    assert q['implicit_self']>0 and work['promotions']>0 and work['masked_displacements']>0
                if kind=='derived':
                    assert q['implicit_self']==q['inline_single']==q['pages']==0
                    assert q['forward_derived']>=q['forward_derived_solo']>0
                    assert work['derived_displacements']==work['derived_solo_displacements']+work['derived_mixed_displacements']>0
                    assert work['derived_mixed_displacements']>0 and work['audited_other_readers']>0
                assert measured['state']==arms[kind]['state_sha'] and measured['root_allocated']==arms[kind]['root_allocated']
                assert measured['peak_rss']>=measured['total']>0
                assert measured['total']==sum(measured[k] for k in ('tree','masks','inline')) and measured['graph']==measured['total']+measured['remainder']
            assert arms['derived' if 'derived' in required else 'owner']['directory']['tree_edges']<arms['empty']['directory']['tree_edges']
    return fixed


if __name__=='__main__':print('Verified ordered complete union domains, physical source and reverse/cache teardown across',len(verify(HERE)),'source programs')
