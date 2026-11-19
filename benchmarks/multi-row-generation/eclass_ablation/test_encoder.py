"""Independent structural and causal checks on alias augmentation of a common template."""
import copy
import unittest

import torch

from encoder import ARMS, EClassEncoder, EClassSchema, certified_partition, permute_class_storage, select_state


def fixture():
    # The three alias ports have different ordered provenance; the fourth port
    # is unrelated. Two independent producer effects imply a transitive class.
    graph = dict(nodes=[dict(kind='read', sort='none', ordinal=0)] + [
        dict(kind='port', sort='eq', ordinal=i) for i in range(4)],
        edges=[[0,'reads',i+1] for i in range(4)] + [[4,'published_to',2]])
    cert = dict(sort='Expr', operation=3, visible_from_stage=1, guard='producer_committed')
    return dict(id='example', version='r1', graph=graph,
                ports=[dict(node=i+1, sort='Expr') for i in range(4)],
                certificates=[dict(cert,left_port=0,right_port=1),
                              dict(cert,left_port=1,right_port=2,operation=4)])


class EClassContracts(unittest.TestCase):
    def setUp(self):
        torch.manual_seed(47)
        self.t=fixture();self.schema=EClassSchema([self.t]);self.model=EClassEncoder(self.schema,12).eval()

    def bank(self, arm, transport='physical', template=None):
        return self.schema.bank(self.t if template is None else template,arm,'cpu',transport)

    def test_admission_and_physical_port_identity(self):
        for arm in ARMS:
            bank=self.bank(arm);self.assertEqual(bank.indices[:3],(0,0,0))
            self.assertEqual(len(bank.views),2 if arm in ('pairwise','incidence') else 1)
            table=self.model.encode_bank(bank)
            self.assertEqual(tuple(table.shape),(4,4,12))
            for s in range(1,3):torch.testing.assert_close(table[0],table[s],rtol=0,atol=0)
            if arm in ('pairwise','incidence'):
                self.assertGreater(float((table[3]-table[0]).detach().abs().max()),1e-6)
                self.assertGreater(float((table[3,0]-table[3,1]).detach().abs().max()),1e-6)
        self.assertEqual(certified_partition(self.t,1,True),((0,1,2),(3,)))
        bad=copy.deepcopy(self.t);bad['ports'][0]['sort']='Other'
        with self.assertRaises(ValueError):self.bank('incidence',template=bad)
        bad=copy.deepcopy(self.t);bad['certificates'][0]['guard']='external_union'
        with self.assertRaises(ValueError):self.bank('pairwise',template=bad)
        bad=copy.deepcopy(self.t);bad['certificates'][0]['scope']='outside-instance'
        with self.assertRaises(ValueError):self.bank('pairwise',template=bad)

    def test_same_information_and_matched_receive(self):
        direct=self.bank('pairwise');inc=self.bank('incidence');p=direct.views[-1];i=inc.views[-1]
        # Check actual encoded graph, not just the certificate list used to build it.
        p_edges=p.adjacency[-1].index_select(0,p.port_nodes).index_select(1,p.port_nodes)>0
        port_class=i.adjacency[-1,i.port_nodes,i.stats['base_nodes']:]>0
        sharing=(port_class.float()@port_class.float().T)>0
        torch.testing.assert_close(sharing,p_edges|torch.eye(4,dtype=torch.bool))
        self.assertEqual(p.stats['alias_directed_messages'],6)
        self.assertEqual(i.stats['alias_directed_messages'],8)
        m_direct=self.model.encode_bank(self.bank('pairwise','matched'))
        m_inc=self.model.encode_bank(self.bank('incidence','matched'))
        torch.testing.assert_close(m_inc,m_direct,rtol=2e-5,atol=2e-6)
        self.assertTrue(torch.isfinite(m_inc).all())

    def test_same_graph_different_instances_and_cache_lifetime(self):
        bank=self.bank('incidence');stage=torch.tensor([[1,1],[0,1]]);receipt=torch.tensor([[True,False],[True,True]])
        with torch.inference_mode():
            table=self.model.frozen_bank(bank)
            self.assertIs(table,self.model.frozen_bank(bank))
            used=select_state(table,stage,receipt)
            self.assertEqual(used.shape,(2,2,4,12))
            torch.testing.assert_close(used[0,0],table[3],rtol=0,atol=0)
            torch.testing.assert_close(used[0,1],table[0],rtol=0,atol=0)
            torch.testing.assert_close(used[1,0],table[0],rtol=0,atol=0)
            other=receipt.clone();other[0,0]=False
            changed=select_state(table,stage,other)
            torch.testing.assert_close(changed[0,1],used[0,1],rtol=0,atol=0)
            torch.testing.assert_close(changed[1],used[1],rtol=0,atol=0)
            revised=copy.deepcopy(self.t);revised['version']='r2';revised['certificates']=[]
            table2=self.model.frozen_bank(self.bank('incidence',template=revised))
            torch.testing.assert_close(table2[3],table[0],rtol=0,atol=0)
            # Identical external events attached only as provenance cannot change
            # any template relation, gate or embedding for a second instance.
            external=copy.deepcopy(self.t);external['external_union_events']=[(11,0,29,3)]
            self.assertIs(self.model.frozen_bank(self.bank('incidence',template=external)),table)
            self.model.direct.weight.add_(0.125)
            refreshed=self.model.frozen_bank(bank)
            self.assertIsNot(refreshed,table)
            self.assertGreater(float((refreshed-table).abs().max()),1e-6)
        with self.assertRaises(RuntimeError):self.model.frozen_bank(bank)
        with torch.inference_mode():
            untracked=EClassEncoder(self.schema,12).eval()
            with self.assertRaisesRegex(RuntimeError,'outside inference_mode'):
                untracked.frozen_bank(bank)

    def test_node_class_and_port_renumberings(self):
        original=self.t['graph'];new=copy.deepcopy(self.t)
        perm=[3,0,4,1,2];rev={old:j for j,old in enumerate(perm)}
        new['graph']['nodes']=[original['nodes'][i] for i in perm]
        new['graph']['edges']=[[rev[x],label,rev[y]] for x,label,y in reversed(original['edges'])]
        for port in new['ports']:port['node']=rev[port['node']]
        ports=[2,0,3,1];reverse_port={old:j for j,old in enumerate(ports)}
        new['ports']=[new['ports'][i] for i in ports]
        for cert in new['certificates']:
            for k in ('left_port','right_port'):cert[k]=reverse_port[cert[k]]
        for arm in ARMS:
            original_table=self.model.encode_bank(self.bank(arm))
            renamed=self.model.encode_bank(self.bank(arm,template=new))
            torch.testing.assert_close(renamed,original_table[:,ports],rtol=2e-5,atol=2e-6)
        for transport in ('physical','matched'):
            view=self.bank('incidence',transport).views[-1]
            shuffled=permute_class_storage(view,torch.tensor([1,0]))
            torch.testing.assert_close(self.model(shuffled),self.model(view),rtol=2e-5,atol=2e-6)


if __name__=='__main__':
    torch.set_num_threads(1)
    unittest.main()
