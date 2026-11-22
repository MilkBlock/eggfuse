"""Check versioned cache updates, order independence, and compatibility of omitted context."""
import torch

from model import Actor, HIDDEN, ROWS
from port_context import ExportMemory, PortContextActor
from port_context_study import FEATURES, inputs, updates


@torch.no_grad()
def check():
    torch.manual_seed(42)
    torch.set_num_threads(1)
    base = Actor().eval()
    torch.manual_seed(42)
    actor = PortContextActor(FEATURES).eval()
    rows = [('L',0), ('R',0), ('R',1)]
    obs,prev,*_ = inputs([(rows,1)])
    memory = ExportMemory(actor)
    expected = base.step(obs,prev)
    for ports in (None,memory.snapshot()):
        actual = actor.step(obs,prev,ports=ports)
        assert all(torch.equal(a,b) for a,b in zip(expected,actual))
    fields = updates(rows)
    memory.publish(fields)
    first = actor.step(obs,prev,ports=memory.snapshot())[0]
    memory.publish(fields)
    assert memory.encoded == 3
    replacement = (1,updates([('R',3)])[1][1])
    memory.publish({2:replacement},retired=[3])
    assert memory.encoded == 4
    current = memory.snapshot()
    fresh = ExportMemory(actor)
    fresh.publish({2:replacement,1:fields[1]})
    assert all(torch.equal(a,b) for a,b in zip(current,fresh.snapshot()))
    assert not torch.equal(first,actor.step(obs,prev,ports=current)[0])
    try:
        memory.publish({2:fields[2]})
    except ValueError:
        pass
    else:
        raise AssertionError('stale replacement accepted')
    # A padded batch without a visible port must exactly preserve the blind path.
    masked = (*current[:2],torch.zeros_like(current[2]))
    assert torch.equal(actor.step(obs,prev,ports=masked)[0],expected[0])
    assert expected[1].shape==(1,ROWS,HIDDEN+4)


if __name__=='__main__':
    check()
