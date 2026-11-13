import unittest
from subcell_views import compile_layout, project

EQ = dict(name='Expr', kind='eq')


class Views(unittest.TestCase):
    def table(self, name='F', kind='constructor', schema=None):
        return dict(name=name, kind=kind, schema=schema or [EQ, EQ])

    def test_cross_program_ids_not_layout_identity(self):
        pattern = [(0, (0,1)), (1, (1,2))]
        a, reason = compile_layout(pattern, [self.table(), self.table('G')])
        b, _ = compile_layout([(1,(0,1)), (0,(1,2))], [self.table('G'), self.table()])
        self.assertIsNone(reason)
        self.assertEqual(a, b)

    def test_mutable_and_incorrect_schema_not_admitted(self):
        self.assertEqual(compile_layout([(0,(0,1))], [self.table(kind='function')])[1], 'mutable_or_relation')
        self.assertEqual(compile_layout([(0,(None,1))], [self.table()])[1], 'column_sort_mismatch')

    def test_shared_port_requires_same_sort(self):
        other = dict(name='Type', kind='eq')
        tables = [self.table(), self.table('G', schema=[other, EQ])]
        self.assertEqual(compile_layout([(0,(0,1)), (1,(1,2))], tables)[1], 'port_sort_conflict')

    def test_view_references_original_ports(self):
        s = dict(components=[dict(id=9, frames=[77], shape=0)],
                 shapes=[dict(programs=[0], ports=[[40,50,60]])],
                 programs=[dict(fields=[[0,1], [1,2]])])
        fields, ports = project(s, [(77,0), (77,1)])
        self.assertEqual(fields, [[0,1], [1,2]])
        self.assertEqual(ports, [dict(component=9,symbol=i) for i in (40,50,60)])

    def test_scalar_is_existing_field_projection_not_a_value_copy(self):
        scalar = dict(name='i64', kind='i64')
        layout, reason = compile_layout([(0,(None,0))], [self.table(schema=[scalar, EQ])])
        self.assertIsNone(reason)
        self.assertEqual(layout['operations'][0]['columns'], [0,1])
        s = dict(components=[dict(id=9, frames=[77], shape=0)],
                 shapes=[dict(programs=[0], ports=[[40]])],
                 programs=[dict(fields=[[None,0]])])
        fields, ports = project(s, [(77,0)])
        self.assertEqual(fields, [[0,1]])
        self.assertEqual(ports, [dict(fact=[77,0],column=0), dict(component=9,symbol=40)])
