import unittest

from compile_plan import compile_instance


class ConstructorCertificate(unittest.TestCase):
    def test_table_order_literal_and_preexisting_identity(self):
        def eq(v):return {'sort':'E','eq':str(v)}
        def literal(v):return {'sort':'i64','value':v}
        def row(t,args):return dict(table=t,values=args,subsumed=False)
        initial=[row('Observe',[literal(o*16+p),eq(o*3+p),eq(20+o*3+p)])
                 for o in (0,1) for p in range(3)]
        initial.extend([row('F',[eq(0),eq(1),literal(4),eq(2)]),
                        row('F',[eq(4),eq(3),literal(4),eq(5)]),
                        row('F',[eq(4),eq(3),literal(5),eq(7)]),
                        row('G',[eq(4),eq(3),literal(4),eq(8)])])
        tables=[{'name':n,'kind':k} for n,k in [('F','constructor'),('G','constructor'),('Observe','relation')]]
        template={'public_ports':[0,1,2],'certificates':[{'left_port':0,'right_port':1}]}
        plan=compile_instance(template,{'rows':initial},tables)
        rule,=plan['implications'];a,b=plan['public']
        self.assertEqual(rule['table'],'F')
        self.assertEqual(rule['requires'],[[a[0],b[1]],[a[1],b[0]]])
        self.assertEqual(rule['unifies'],[a[2],b[2]])
