"""Produce a separate larger native corpus without retaining thousands of loose files."""

import copy
import tarfile
from pathlib import Path
from tempfile import TemporaryDirectory

import torch

from cell_kv_runtime import native
from partner_index_worlds import args
from rule_read import load_actor
from value_read_world import CUBES, SCHEMAS, field_pair, instance


def prepare(a):
    actor = load_actor(a.actor, True)
    rows = {}
    with tarfile.open(
        a.out / "native-filler.tar.gz", "w:gz", compresslevel=1
    ) as archive:
        for schema in SCHEMAS:
            # Every schema sees all the same three-field truth cubes and fillers.
            for pool in range(72001, 72033):
                for bits in CUBES:
                    with TemporaryDirectory() as temp:
                        b = copy.copy(a)
                        b.out = Path(temp)
                        w = instance(b, actor, schema, pool, bits)
                        values = native(b, w, teacher="higher")
                        (t,) = [t for t, r in values[0][1] if t >= w.primitives]
                        j, k = field_pair(schema[0])
                        assert t - w.primitives == (schema[1] ^ (bits[j] != bits[k]))
                        rows[w.dir.name] = values
                        archive.add(w.dir, arcname=w.dir.name)
            print(schema, len(rows), flush=True)
    torch.save(rows, a.out / "corpus-rich.pt")


if __name__ == "__main__":
    torch.set_num_threads(1)
    prepare(args())
