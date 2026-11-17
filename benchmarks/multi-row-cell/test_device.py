import unittest
import numpy as np
import mlx.core as mx
from catalog import Catalog,leaf,ref,ABSENT
from device import Device,LIVE,FORWARD,UNPUBLISHED,STALE,HOP_BUDGET,replace_at
from reference import SourceGraph,packet_term
from rotary import key,rebase,select

def fixture(rows=3,length=4):
    c=Catalog();f=c.add('F',('x',),[('f',10,('x',),1)])
    h=c.add('H',('y','c'),[('h',20,('y','c'),2)])
    plan=c.compose(f,h,{'y':'f'},'FH')
    instances=[(0,1,f,[leaf(7)],0),(1,2,h,[ref(0,1,1),leaf(11)],1),
               (2,0,f,[leaf(91)],2)]
    d=Device(c,rows,length,arena_capacity=4)
    proposal=mx.array([plan,0,1,1,1,2,1,0,3,0,0],mx.int32)
    return c,d,instances,proposal


def host(r):
    mx.eval(r);return {k:np.array(v) for k,v in r.items()}

class DeviceContracts(unittest.TestCase):
    def assert_source(self,c,d,instances,packet,run):
        source=SourceGraph(c,instances)
        for row,pos,tpl,_,_ in instances:
            for port in range(len(c.templates[tpl].ports)):
                q=ref(row,pos,port)
                self.assertEqual(packet_term(packet,q,d.length),source.term(q,run),q)

    def test_cross_row_composition_before_later_run(self):
        c,d,instances,proposal=fixture();initial=d.initialize(instances)
        def execute(s):
            s,one=d.publish(s,1,rounds=2)
            before=d.view(s,d.all_queries())
            s,transfer=d.transfer(s,proposal)
            pending=d.view(s,mx.array([ref(1,2,2)]))
            s,two=d.publish(s,2,rounds=2)
            after=d.view(s,d.all_queries())
            return s,one,transfer,pending,two,before,after
        state,one,tr,pending,two,before,after=mx.compile(execute)(initial)
        mx.eval(state,one,tr,pending,two,before,after)
        self.assertTrue(bool(tr['accepted']));self.assertEqual(int(one['pending']),0);self.assertEqual(int(two['pending']),0)
        self.assertFalse(bool(pending['valid'][0]));self.assertEqual(int(pending['error'][0]),UNPUBLISHED)
        self.assert_source(c,d,instances,host(before),1);self.assert_source(c,d,instances,host(after),2)
        self.assertEqual(int(mx.sum(state['arena_owner']>=0)),2)
        self.assertEqual(int(mx.sum(state['kind']==LIVE)),2)
        self.assertEqual(int(mx.sum(state['kind']==FORWARD)),2)
        freed=int(tr['released_payload']);poisoned=dict(state)
        poisoned['arena']=replace_at(state['arena'],freed,mx.full((d.params,4),-777,mx.int32))
        self.assert_source(c,d,instances,host(d.view(poisoned,d.all_queries())),2)
        # New physical owner is in row 0; old source row 1 still resolves to it.
        q=mx.array([ref(1,2,2)]);r=d.resolve(state,q);mx.eval(r)
        self.assertEqual(np.array(r['reference'])[0,:2].tolist(),[0,3])
        translated=rebase(key(q),q,r['reference']);mx.eval(translated)
        np.testing.assert_allclose(translated,key(r['reference']),atol=1e-6)

    def test_reject_stale_generation_wrong_wiring_and_destination(self):
        c,d,instances,p=fixture();s=d.initialize(instances)
        for offset,value in [(3,2),(9,3),(7,9)]:
            bad=replace_at(p,offset,mx.array(value,mx.int32));out,tr=d.transfer(s,bad);mx.eval(out,tr)
            self.assertFalse(bool(tr['accepted']))
            for k in s:np.testing.assert_array_equal(s[k],out[k])
        bad_instances=list(instances);bad_instances[1]=(1,2,1,[ref(2,0,1),leaf(11)],1)
        s=d.initialize(bad_instances);out,tr=d.transfer(s,p);mx.eval(tr)
        self.assertFalse(bool(tr['accepted']))

    def test_overlapping_retirement_rejects_later_row(self):
        c,d,instances,p=fixture();s=d.initialize(instances)
        duplicate=replace_at(p,8,mx.array(0,mx.int32))
        out,r=mx.compile(d.transfer_batch)(s,mx.stack((p,duplicate)))
        mx.eval(out,r);self.assertEqual(np.array(r['accepted']).tolist(),[True,False])
        self.assertEqual(int(mx.sum(out['arena_owner']>=0)),2)

    def test_row_position_port_axes_and_joint_lookup(self):
        coordinates=mx.array([ref(r,t,p) for r in range(4) for t in range(9) for p in range(3)])
        wanted=mx.array([ref(1,2,0),ref(2,1,0),ref(3,8,2),ref(0,0,1)])
        selected,valid=select(key(wanted),coordinates,mx.ones((len(coordinates),),mx.bool_));mx.eval(selected,valid)
        np.testing.assert_array_equal(selected,wanted)
        self.assertFalse(np.allclose(key(wanted[:1]),key(wanted[1:2])))
        moved=mx.array([ref(3,4,2),ref(2,2,1),ref(0,1,0),ref(1,5,2)])
        np.testing.assert_allclose(rebase(key(wanted),wanted,moved),key(moved),atol=1e-6)

    def test_stale_address_cannot_read_reused_coordinate(self):
        c,d,instances,_=fixture();s=d.initialize(instances);s,_=d.publish(s,1)
        # Simulate a new generation at the same coordinate; rotary key is unchanged.
        s=dict(s);idx=0*d.length+1;s['generation']=replace_at(s['generation'],idx,mx.array(2,mx.int32))
        r=d.resolve(s,mx.array([ref(0,1,1,1),ref(0,1,1,2)]));mx.eval(r)
        self.assertEqual(np.array(r['valid']).tolist(),[False,True]);self.assertEqual(int(r['error'][0]),STALE)

    def test_alias_cycle_budget_is_not_success(self):
        c,d,instances,_=fixture();bad=list(instances)
        bad[0]=(0,1,0,[ref(1,2,0)],0);bad[1]=(1,2,1,[ref(0,1,0),leaf(11)],1)
        s=d.initialize(bad);r=d.resolve(s,mx.array([ref(0,1,0)]));mx.eval(r)
        self.assertFalse(bool(r['valid'][0]));self.assertEqual(int(r['error'][0]),HOP_BUDGET)
        _,progress=d.publish(s,1,rounds=2);mx.eval(progress);self.assertGreater(int(progress['pending']),0)

    def test_compiler_rejects_invalid_orders_and_handles_nested_composition(self):
        c=Catalog();f=c.add('F',('x',),[('f',10,('x',),2)])
        h=c.add('H',('y',),[('h',20,('y',),1)])
        with self.assertRaises(ValueError):c.compose(f,h,{'y':'f'},'bad')
        c=Catalog();f=c.add('F',('x',),[('f',10,('x',),1)])
        h=c.add('H',('y',),[('h',20,('y',),2)])
        ph=c.compose(f,h,{'y':'f'},'FH');m=c.compositions[ph].target
        g=c.add('G',('z',),[('g',30,('z',),3)])
        pm=c.compose(m,g,{'z':'R.h'},'FHG');t=c.templates[c.compositions[pm].target]
        self.assertEqual(len(t.parameters),1)
        self.assertEqual([p.opcode for p in t.ports if p.binding<0],[10,20,30])
        self.assertEqual(len({p.name for p in t.ports}),len(t.ports))

    def test_unfinished_run_cannot_advance(self):
        c,d,instances,_=fixture();s=d.initialize(instances)
        s,first=d.publish(s,1,rounds=0)
        blocked,second=d.publish(s,2,rounds=2);mx.eval(s,first,blocked,second)
        self.assertGreater(int(first['pending']),0);self.assertFalse(bool(second['schedule_ok']))
        for k in s:np.testing.assert_array_equal(s[k],blocked[k])
        s,retry=d.publish(s,1,rounds=2);s,last=d.publish(s,2,rounds=2);mx.eval(retry,last)
        self.assertEqual(int(retry['pending']),0);self.assertTrue(bool(last['schedule_ok']))
        self.assert_source(c,d,instances,host(d.view(s,d.all_queries())),2)

    def test_nested_takeover_keeps_forwarded_inputs(self):
        c,d0,instances,first=fixture()
        m=c.compositions[0].target
        g=c.add('G',('z',),[('g',30,('z',),3)])
        second_plan=c.compose(m,g,{'z':'R.h'},'FHG')
        instances=instances+[(1,0,g,[ref(1,2,2)],1)]
        d=Device(c,3,4,arena_capacity=4);s=d.initialize(instances)
        second=mx.array([second_plan,0,3,1,1,0,1,2,3,0,2],mx.int32)
        def execute(state):
            state,_=d.publish(state,1,rounds=2)
            state,a=d.transfer(state,first)
            state,_=d.publish(state,2,rounds=2)
            state,b=d.transfer(state,second)
            hidden=d.view(state,mx.array([ref(1,0,1)]))
            state,complete=d.publish(state,3,rounds=2)
            return state,a,b,hidden,complete,d.view(state,d.all_queries())
        out,a,b,hidden,complete,packet=mx.compile(execute)(s);mx.eval(out,a,b,hidden,complete,packet)
        self.assertTrue(bool(a['accepted']) and bool(b['accepted']))
        self.assertFalse(bool(hidden['valid'][0]));self.assertEqual(int(complete['pending']),0)
        self.assert_source(c,d,instances,host(packet),3)
        self.assertEqual(int(mx.sum(out['arena_owner']>=0)),2)
        self.assertEqual(int(mx.sum(out['kind']==FORWARD)),4)
        # Old producer references now traverse two distinct shared projections.
        r=d.resolve(out,mx.array([ref(0,1,1)]));mx.eval(r)
        self.assertEqual(np.array(r['reference'])[0,:2].tolist(),[2,3])

    def test_one_graph_contains_coupled_cross_row_pairs(self):
        c=Catalog();f=c.add('F',('x',),[('f',10,('x',),1)])
        h=c.add('H',('y','c'),[('h',20,('y','c'),2)])
        plan=c.compose(f,h,{'y':'f'},'FH')
        rng=np.random.default_rng(712);rows,length,pairs=4,8,6
        slots=rng.permutation(rows*length)[:3*pairs].reshape(pairs,3)
        coordinates=[[(int(x)//length,int(x)%length) for x in group] for group in slots]
        instances=[];proposals=[]
        for i,((fr,ft),(hr,ht),(dr,dt)) in enumerate(coordinates):
            neighbor=coordinates[(i+1)%pairs][0]
            instances.extend([(fr,ft,f,[leaf(500+i)],fr),(hr,ht,h,[ref(fr,ft,1),ref(*neighbor,1)],hr)])
            proposals.append([plan,fr,ft,1,hr,ht,1,dr,dt,0,dr])
        d=Device(c,rows,length,arena_capacity=2*pairs)
        def execute(state):
            state,_=d.publish(state,1,rounds=2)
            state,take=d.transfer_batch(state,mx.array(proposals,mx.int32))
            state,complete=d.publish(state,2,rounds=2)
            return state,take,complete,d.view(state,d.all_queries())
        state,take,complete,packet=mx.compile(execute)(d.initialize(instances));mx.eval(state,take,complete,packet)
        self.assertTrue(bool(mx.all(take['accepted'])));self.assertEqual(int(complete['pending']),0)
        self.assert_source(c,d,instances,host(packet),2)
        self.assertEqual(int(mx.sum(state['arena_owner']>=0)),pairs)
        # Arena was completely full initially; target admission reuses source storage.
        self.assertEqual(state['arena'].shape[0],2*pairs)

    def test_rotary_lookup_reads_shared_view_and_rejects_wrong_pointer(self):
        c,d,instances,p=fixture();s=d.initialize(instances)
        def execute(state):
            state,_=d.publish(state,1,rounds=2);state,_=d.transfer(state,p)
            state,_=d.publish(state,2,rounds=2)
            requested=mx.array([ref(0,1,1),ref(1,2,2),ref(2,0,1)])
            good=d.read_encoded(state,key(requested),requested)
            bad=d.read_encoded(state,key(requested),requested[::-1])
            return good,bad
        good,bad=mx.compile(execute)(s);mx.eval(good,bad)
        self.assertEqual(np.array(good['valid']).tolist(),[True,True,True])
        self.assertEqual(np.array(good['opcode']).tolist(),[10,20,10])
        self.assertEqual(np.array(bad['valid']).tolist(),[False,True,False])
        self.assertEqual(np.array(good['reference'])[1,:2].tolist(),[0,3])

    def test_corrupt_descriptor_bounds_do_not_alias_clamped_storage(self):
        c,d,instances,_=fixture();s=d.initialize(instances);s,_=d.publish(s,1,rounds=2)
        q=mx.array([ref(2,0,1)]);i=2*d.length
        for field,value in [('payload',d.capacity+2),('template',len(c.templates)+3),('template',-1)]:
            broken=dict(s);broken[field]=replace_at(s[field],i,mx.array(value,mx.int32))
            result=d.resolve(broken,q);mx.eval(result)
            self.assertFalse(bool(result['valid'][0]))

if __name__=='__main__':unittest.main()
