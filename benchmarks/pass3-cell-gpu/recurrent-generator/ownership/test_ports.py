import unittest
from ports import Port, Transfers


class PortAudit(unittest.TestCase):
    def test_scoped_transitive_move(self):
        a,b,c=(Port(i,7,3) for i in (1,2,3))
        side=Port(1,8,3)
        log=Transfers()
        log.publish(a,"result")
        log.publish(side,"other")
        log.transfer(a,b,4)
        with self.assertRaises(ValueError):
            log.transfer(a,c,5)
        with self.assertRaises(ValueError):
            log.transfer(b,c,3)
        log.transfer(b,c,6)
        got=log.audit([(a,10),(b,10),(c,10),(c,10),(c,11),(side,10),(Port(3,7,2),10)])
        self.assertEqual(got,dict(active=7,retired=2,duplicate=1,unknown=1,novel=3))


if __name__=="__main__":
    unittest.main()
