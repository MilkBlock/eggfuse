"""Check counts, prior source identities, donor-only shape selection, exact trace examples and transfers."""
from collections import Counter
import json
from pathlib import Path
from hashlib import sha256
HERE=Path(__file__).resolve().parent
def digest(x):return sha256(json.dumps(x,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def main():
    read=lambda x:json.loads((HERE/(x+'.json')).read_bytes())
    counts=read('shape-counts');a=read('results');cat=read('catalog');tr=read('transfer')
    order=counts['order'];assert order==['dot-product','jacobi-1d','sum-bits','3mm']
    cases={k:{o:{} for o in ('pairs','triples')} for k in order};definitions={};seen=set()
    for key,s,v in counts['shapes']:
        assert key not in seen;seen.add(key)
        if len(s)==5:kind='pairs';shape=s;pr,ch,gap,wires,n=s;assert gap>0 and len(wires)==n and len({w[0] for w in wires})==n
        else:
            kind='triples';i,j,n=s;shape=[counts['shapes'][i][0],counts['shapes'][j][0],n]
            assert digest(shape[:2])==key
        definitions[key]=shape
        for case,x in zip(order,v):
            if not x:continue
            if kind=='pairs':
                rules=counts['rule_fingerprints'][case];assert digest([rules[pr],rules[ch],gap,wires])==key
            cases[case][kind][key]=x
    for c in order:
        r=a[c];s=r['counts'];assert all(r['reference']['checks'].values())
        assert sum(sum(x.values()) for x in r['census'].values())==s['root_commits']==r['reference']['rhs']
        assert sum(cases[c]['pairs'].values())==s['pair_children']==sum(r['pair_categories'].values())
        assert sum(cases[c]['triples'].values())==s['chain_terminal_children']==sum(r['triple_terminal_categories'].values())
        for name,e in r['examples'].items():
            if 'producer' not in e:continue
            p=e['producer'];child=e['child'];assert p['run']<child['run'] and p['ordinal']<child['ordinal']
            src={row[0]:row[1:] for row in p['named']};refs={row[0]:row[1:] for row in child['named']}
            births={b[4]:b for b in e['newly_born_evidence']};assert len(e['wiring'])==len(refs)
            for atom,which,port in e['wiring']:
                row=refs[atom]
                if which=='input':assert row==src[port]
                else:assert row[1]=='Fact' and row[2] in births and row[2]&0xffffffff==port and row[3]==p['epoch']
    for kind in ('pairs','triples'):
        donors=Counter(cases[order[0]][kind]);donors.update(cases[order[1]][kind])
        assert set(cat[kind])=={s for s,n in donors.items() if n>=2}
        for select,test in [('seen',lambda k:donors[k]>0),('repeated',lambda k:donors[k]>=2),('both_donors',lambda k:all(k in cases[c][kind] for c in order[:2]))]:
            selected={k for k in donors if test(k)};z=tr[kind][select];assert len(selected)==z['shapes']
            assert sum(donors[k] for k in selected)==z['donor_occurrences']
            for c in order[2:]:
                total=Counter()
                for k in selected&cases[c][kind].keys():
                    s=definitions[k] if kind=='pairs' else definitions[definitions[k][1]]
                    typ='unary' if s[-1]==1 else 'multi_distinct_refs' if len({tuple(w[1:]) for w in s[3]})>1 else 'multi_aliased_single_ref'
                    total[typ]+=cases[c][kind][k]
                assert dict(total)==z['heldout'][c]['children']
    print('Verified four ordinary named-root Pass 3 ledgers, ordered typed wiring and physical identity examples, duplicate-free occurrence counts and donor-only pair/triple shape transfer.')
if __name__=='__main__':main()
