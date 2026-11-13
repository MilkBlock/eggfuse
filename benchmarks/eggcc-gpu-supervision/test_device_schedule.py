import unittest
import numpy as np
import mlx.core as mx
from device_schedule import compile_schedule,initial,current,tick


def reference(node,events,counts):
    if isinstance(node,list):
        changed=False
        for child in node:changed=reference(child,events,counts) or changed
        return changed
    if 'sequence' in node:return reference(node['sequence'],events,counts)
    if 'run' in node:
        name=node['run'];n=counts.get(name,0);counts[name]=n+1;events.append(name)
        return name=='a' and n==0
    if 'repeat' in node:
        changed=False
        for _ in range(node['repeat']):changed=reference(node['body'],events,counts) or changed
        return changed
    changed=False
    while True:
        again=reference(node['saturate'],events,counts);changed=changed or again
        if not again:return changed


class Schedule(unittest.TestCase):
    def test_nested_saturation_propagates_changes_to_outer_loop_on_gpu(self):
        control=dict(saturate=dict(sequence=[dict(saturate=dict(run='a')),dict(run='b')]))
        plan,meta=compile_schedule(control,['a','b']);expected=[];reference(control,expected,{})
        self.assertEqual(expected,['a','a','b','a','b'])
        if not mx.metal.is_available():self.skipTest('Metal required')
        dp={k:mx.array(v) for k,v in plan.items()}
        def execute():
            s=initial(dp,meta['repeat_slots'],mx);seen=mx.array(0);events=[]
            for _ in range(32):
                stage,_=current(s,dp,mx);change=(stage==0)&(seen==0)
                s,m=tick(s,dp,mx.array(True),change,mx)
                seen=seen+((stage==0)&m['run_consumed']).astype(mx.int32);events.append(stage)
            _,finished=current(s,dp,mx)
            return mx.stack(events),finished
        events,finished=mx.compile(execute)();mx.eval(events,finished)
        actual=[['a','b'][i] for i in np.array(events) if i>=0]
        self.assertEqual(actual,expected);self.assertTrue(bool(finished))

    def test_repeat_zero_nested_repeat_and_wait(self):
        control=[dict(repeat=0,body=dict(run='a')),dict(repeat=2,body=dict(sequence=[dict(run='a'),dict(repeat=2,body=dict(run='b'))]))]
        p,m=compile_schedule(control,['a','b']);s=initial(p,m['repeat_slots'],np);events=[]
        for _ in range(40):
            stage,finished=current(s,p,np)
            if stage>=0:
                before={k:v.copy() for k,v in s.items()};s,mark=tick(s,p,False,True,np)
                for k in s:np.testing.assert_array_equal(s[k],before[k])
                self.assertTrue(mark['waiting']);events.append(['a','b'][stage])
            s,_=tick(s,p,True,False,np)
        expected=[];reference(control,expected,{})
        self.assertEqual(events,expected);self.assertTrue(current(s,p,np)[1])

    def test_invalid_controls_and_pc_fail_explicitly(self):
        for control in ({'run':'unknown'},{'repeat':-1,'body':[]},{'saturate':[],'until':True}):
            with self.assertRaises(ValueError):compile_schedule(control,['a'])
        p,m=compile_schedule([],['a']);s=initial(p,0,np);s['pc']=np.array(999,np.int32)
        after,marks=tick(s,p,True,True,np);self.assertTrue(marks['invalid_pc']);self.assertEqual(after['pc'],999)


if __name__=='__main__':unittest.main()
