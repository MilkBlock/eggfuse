from pathlib import Path
import hashlib
import numpy as np

HERE = Path(__file__).resolve().parent
TRAIN = ((2,3,2), (2,4,3), (3,4,2), (4,3,3))
ARMS = ('flat','two','three','packed')
SEEDS = (1703,1709)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def input_digest(data):
    h = hashlib.sha256()
    for k in ('coords','make_ref','finish_ref','value','target1','target2'):
        arr = np.ascontiguousarray(data[k])
        h.update(k.encode()); h.update(arr.tobytes())
    return h.hexdigest()


def panels():
    from data import dataset, relayout
    result = {}; pairs = {}
    def base(name, shape, seed):
        result[name] = (*shape, dataset(*shape,128,seed))
    def move(name, source, rows, length, seed):
        _,_,ports,old = result[source]
        new,mapping = relayout(old,rows,length,seed)
        result[name] = (rows,length,ports,new)
        pairs[name] = (source,mapping)
    base('seen',(4,3,3),92001)
    move('same_shuffle','seen',4,3,92101)
    move('new_rows','seen',6,2,92102)
    move('new_length','seen',2,6,92103)
    base('new_port',(4,3,4),92002)
    move('rows_port','new_port',6,2,92104)
    base('large',(8,6,4),92003)
    move('large_shuffle','large',4,12,92105)
    return result,pairs
