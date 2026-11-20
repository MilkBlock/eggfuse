"""Construct original and changed-port generation requests for exactly the same compiled program."""
from pathlib import Path
import json,sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'native-backend-pgo'))
from pgo_common import DONORS,HOLDOUTS,file_digest,inputs,session,source
sys.path.insert(0,str(HERE.parent/'request-route-policy'))
from driver import bridge


def routes(a,name):
    p,plan,off=inputs(a,name)
    connections=bridge.extract(json.loads(p.read_bytes()),json.loads(plan.read_bytes()))
    assert any(connections)
    return p,plan,off,dict(off,connected_requests=connections,wake_roots=3,patch_subscriptions=3)
