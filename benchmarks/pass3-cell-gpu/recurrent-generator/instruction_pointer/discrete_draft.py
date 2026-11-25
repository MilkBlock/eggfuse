"""Unissued typed Cell plans, stable local references, and valid conditional edit bridges."""

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Local:
    owner: int
    port: int


@dataclass(frozen=True)
class Cell:
    rule: int
    refs: tuple
    higher: bool = False
    observe: int = 0


@dataclass(frozen=True)
class Item:
    uid: int
    cell: Cell


def plan(tokens):
    return tuple(Item(i, t) for i, t in enumerate(tokens))


def valid(items, compatible=None):
    prefix = {}
    for item in items:
        if item.uid in prefix:
            return False
        for slot, ref in enumerate(item.cell.refs):
            if isinstance(ref, Local):
                if ref.owner not in prefix:
                    return False
                if compatible and not compatible(prefix[ref.owner], ref.port, item.cell, slot):
                    return False
        prefix[item.uid] = item.cell
    return True


def change(items, i, kind, value=None, compatible=None, fresh_uid=None):
    new = list(items)
    if kind == 0:
        uid = 1 + max((v.uid for v in items), default=-1) if fresh_uid is None else fresh_uid
        new.insert(i, Item(uid, value))
    elif kind == 1:
        del new[i]
    elif kind == 2:
        new[i] = replace(new[i], cell=value)
    else:
        raise ValueError(kind)
    return tuple(new) if valid(new, compatible) else items


def script(source, target):
    """A valid ordered bridge. The data builder uses local IDs in topological order."""
    x = source
    path = []
    if not valid(x) or not valid(target):
        raise ValueError("dangling source/target")
    common = 0
    while common < min(len(x), len(target)) and x[common] == target[common]:
        common += 1
    if x == target:
        return []
    # Keep a position for substitution only after its consumers have been removed.
    keep = common + int(common < min(len(x), len(target)))
    for i in reversed(range(keep, len(x))):
        path.append((x, i, 1, None))
        x = change(x, i, 1)
    if keep > common:
        v = target[common].cell
        path.append((x, common, 2, v))
        x = change(x, common, 2, v)
    for i in range(keep, len(target)):
        v = target[i].cell
        path.append((x, i, 0, v))
        x = change(x, i, 0, v)
    if x != target:
        raise ValueError("unrepresentable bridge")
    return path
