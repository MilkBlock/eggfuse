"""Audit provenance from initial logical instance identities, not rule IDs.

Stored once in capture metadata; no new GPU reverse index or mutable registry.
"""
import numpy as np


def initial_instances(state):
    return {str(int(i)):int(state['generation'][i]) for i in np.flatnonzero(state['present'])}


def generated(rows,generations,initial):
    rows=np.asarray(rows);generations=np.asarray(generations)
    if rows.shape!=generations.shape:raise ValueError('source identity shape')
    old=np.zeros(rows.shape,bool)
    for row,epoch in initial.items():old|=(rows==int(row))&(generations==epoch)
    return ~old
