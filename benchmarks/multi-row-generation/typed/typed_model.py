"""Canonicalize ONLY the model's own symbol decisions, never reference values."""
import sys
from pathlib import Path
import mlx.core as mx
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from network import Generator,DIM
from task import KEYS,VALUES

WIDTH=2*KEYS+2*VALUES

def tokenize(scores):
    pieces=[];offset=0
    for width in (KEYS,KEYS,VALUES,VALUES):
        logits=scores[...,offset:offset+width];soft=mx.softmax(logits,axis=-1)
        choice=mx.stop_gradient(mx.argmax(logits,-1));hard=mx.eye(width)[choice]
        # Exact hard symbols in forward; explicit straight-through surrogate in backward.
        pieces.append(mx.stop_gradient(hard)+(soft-mx.stop_gradient(soft)));offset+=width
    symbols=mx.concatenate(pieces,-1)
    return mx.concatenate((symbols,mx.zeros(symbols.shape[:-1]+(DIM-WIDTH,))),-1)

class TypedGenerator(Generator):
    def emit(self,prepared):
        pointer,raw,scores=super().emit(prepared)
        return pointer,tokenize(scores),scores
    def semantic_readout(self):return mx.eye(WIDTH,DIM),mx.zeros((WIDTH,))
