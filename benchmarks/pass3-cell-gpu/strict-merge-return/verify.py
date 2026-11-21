"""Check the archived real native strict merge-return ablation and fault controls."""
from pathlib import Path
import hashlib,json
HERE=Path(__file__).resolve().parent
def read(f):return json.loads((HERE/f).read_bytes())
def main():
    for f,h in read('manifest.json')['files'].items():assert hashlib.sha256((HERE/f).read_bytes()).hexdigest()==h,f
    data=read('results.json');opps=read('opportunities.json');assert set(data)==set(opps)=={'sum-bits','3mm'}
    for name,v in data.items():
        leaf=v['arms']['leaf'];cell=v['arms']['composed'];q=cell['strict'];m=cell['internal']
        for k in ('runs','rhs_count','emitted_roots','owned_births','effective_births','state_sha','digests','root_commits_sha','root_fresh_sha','unions_sha','events_sha','birth_sha','export_original_sha','coalesced_sha'):
            assert leaf[k]==cell[k],(name,k)
        for arm in (leaf,cell):
            assert arm['packets']==sum(arm['emitted_roots'])+arm['selected_children']
            assert arm['fept']==arm['effective_births']/arm['packets']
            assert len(arm['ms'])==len(arm['wall_ms'])==4
        assert q['tagged']+q['missing_named']==q['scope_candidates']
        assert q['tagged']>=q['activated']>=q['armed']>=q['entered']>0
        assert q['fresh']==m['internal_fresh'] and q['interned']==m['internal_interned']
        assert q['fresh']+q['interned']==q['entered'] and q['noop']+q['entered']==q['armed']
        assert m['factory_fresh_on_root']+m['factory_returned_existing']==m['verified_leaf_physical_returns']==q['entered']
        assert 0<m['internal_visible']<=m['internal_fresh']
        assert cell['packets']+m['suppressed_child_proposals']==leaf['packets']
        assert q['tag_bytes']>0 and leaf['strict']['tag_bytes']==0
        assert m['suppressed_child_scores']==leaf['child_candidates']-cell['child_candidates']
        assert m['internal_fresh']+cell['external_child_fresh']==leaf['external_child_fresh']
        assert opps[name]['counts']['named_selected']>=m['suppressed_child_proposals']>0
        for runs,why in v['faults'].values():assert runs<leaf['runs'] and 'strict merge old reference differs' in why
    print('Two full source/physical birth ledgers, paid suppression, actual nested returns and four corruptions verified.')
if __name__=='__main__':main()
