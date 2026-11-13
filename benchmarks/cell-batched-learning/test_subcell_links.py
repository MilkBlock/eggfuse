import unittest
from subcell_links import links


class SubcellLinks(unittest.TestCase):
    def setUp(self):
        value = (1 << 32) | 1
        self.storage = dict(components=[
            dict(id=10,shape=0,frames=[1],signals=[value],roots=[value],frame_codes=[0]),
            dict(id=20,shape=0,frames=[2],signals=[value],roots=[value],frame_codes=[1])],
            shapes=[dict(programs=[0],ports=[[0]])],
            programs=[dict(native={'0':0},fields=[[0]])], operators=[[7],[8]])
        self.frames = [dict(cell=1,facts=[dict(op=0,owned=True,hidden=False)]),
                       dict(cell=2,facts=[dict(op=0,owned=True,hidden=False)])]

    def test_same_layout_is_not_same_instance_or_operator(self):
        counts, edges = links(self.storage,self.frames)
        self.assertEqual(counts['cross_component_symbols'],1)
        self.assertEqual(edges[0]['producer'],10)
        self.assertEqual(edges[0]['consumer'],20)
        self.assertEqual(edges[0]['visible_provider_sites'],[(0,0,7)])

    def test_native_address_requires_actual_current_binding(self):
        self.storage['components'][0]['roots'][0] = 123
        counts, edges = links(self.storage,self.frames)
        self.assertEqual(counts['native_address_not_current_binding'],1)
        self.assertEqual(edges,[])

    def test_hidden_fact_does_not_establish_live_provider(self):
        self.frames[0]['facts'][0]['hidden'] = True
        counts, edges = links(self.storage,self.frames)
        self.assertEqual(counts['cross_component_symbols'],1)
        self.assertEqual(counts['cross_component_with_visible_provider'],0)
        self.assertEqual(edges[0]['visible_provider_sites'],[])

    def test_reused_input_is_not_a_native_constructor_slot(self):
        self.storage['programs'][0]['native'] = {}
        counts, edges = links(self.storage,self.frames)
        self.assertEqual(counts['no_native_slot'],2)
        self.assertEqual(edges,[])
