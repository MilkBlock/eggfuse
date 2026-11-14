import copy,unittest
from enumerate_cell_interactions import partitions,Interface,enumerate_interfaces,replay_case


def recipe(literals=False):
    eq=dict(kind='eq',name='E');i64=dict(kind='i64',name='i64')
    if literals:
        rules=[dict(slots=[dict(sort=eq),dict(sort=eq)],query=[dict(call=dict(table='F'),args=[dict(slot=0),dict(literal=n,sort=i64),dict(slot=1)])],effects=[]) for n in [0,1]]
        return dict(tables=[dict(name='F',kind='constructor',schema=[eq,i64,eq])],rules=rules)
    r=dict(slots=[dict(sort=eq) for _ in range(3)],query=[dict(call=dict(table='F'),args=[dict(slot=0),dict(slot=1)])],effects=[dict(kind='construct',call=dict(table='F'),args=[dict(slot=1)],dst=2)])
    return dict(tables=[dict(name='F',kind='constructor',schema=[eq,eq])],rules=[r])

class Enumeration(unittest.TestCase):
    def test_partition_completeness(self):
        self.assertEqual([len(list(partitions(i))) for i in range(6)],[1,1,2,5,15,52])
        self.assertEqual(len(set(partitions(5))),52)

    def test_all_links_and_congruence(self):
        cases,report=enumerate_interfaces(recipe(),10)
        self.assertEqual(report['wirings'],2)
        self.assertTrue(report['within_bound_complete'])
        self.assertEqual({tuple(c['wiring']) for c in cases},{(0,),(1,)})
        for case in cases:
            rows=case['snapshot']['rows'];keys={}
            for row in rows:
                key=str(row['values'][:-1]);value=row['values'][-1]
                self.assertTrue(key not in keys or keys[key]==value);keys[key]=value
        self.assertEqual(enumerate_interfaces(recipe(),10),(cases,report))

    def test_case_replay_rejects_changed_wiring_partition_and_facts(self):
        from synthetic_cell_inputs import validate,digest
        r=recipe();cases,_=enumerate_interfaces(r,10)
        for c in cases:self.assertEqual(replay_case(r,c),c['snapshot'])
        c=cases[0];doc=dict(schema='enumerated-cell-input/v1',recipe=r,recipe_sha256=digest(r),case=c,snapshot=c['snapshot'],input_sha256=c['input_sha256'])
        self.assertEqual(validate(doc),(r,c['snapshot']))
        for mutate in [lambda c:c.update(wiring=[-1]),lambda c:c.update(partition=[[99]]),lambda c:c.update(input_sha256='bad')]:
            bad=copy.deepcopy(c);mutate(bad)
            with self.assertRaises(ValueError):replay_case(r,bad)

    def test_literal_conflicts_and_budget_are_explicit(self):
        _,report=enumerate_interfaces(recipe(True),10)
        self.assertEqual(report['contradictory_wirings'],2)
        _,limited=enumerate_interfaces(recipe(),1)
        self.assertGreater(limited['budget_exclusions'],0)
        self.assertFalse(limited['within_bound_complete'])

if __name__=='__main__':unittest.main()
