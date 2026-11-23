"""Avoid retransmitting standalone requests already owned by a signed compound root."""
from collections import defaultdict


class HigherOwnership:
    def __init__(self, units):
        self.units = units
        self.pending = defaultdict(set)
        self.omitted = 0

    def advance(self, frame, history):
        # Only real root receipts authorize an edge. A residual or rejected
        # proposal cannot arm it. Mirror the native first post-commit version.
        for root in frame['accepted']:
            if 'unit' not in root or root['token'] >= 1 << 61:
                continue
            op, child = self.units[root['unit']]['hops'][0]
            token = root['token']
            row = history.visible.get((token,op))
            if row:
                self.pending[child].add((child,token,op,row['version']))
        current = set()
        for rule,_ in frame['rules']:
            current.update(self.pending.pop(rule,()))
        return current

    def covered(self, claims, rule, parents):
        if len(parents) != 1:
            return False
        ref = parents[0]
        a = ref['address']
        if (rule,a['token'],a['op'],ref['version']) not in claims:
            return False
        self.omitted += 1
        return True
