"""Structured latent ABI. Protected input lanes are carried by GPU transitions."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'structure'))
sys.path.append(str(Path(__file__).resolve().parents[1]))
from spec import INPUT_WIDTH, SPECS, BOOL, OFFSETS, PAIRS, WIDTH
EQ_END=64
PTR_END=EQ_END+72
SEED_END=PTR_END+INPUT_WIDTH
PHASE_END=SEED_END+3
TOKEN_WIDTH=PHASE_END+1
# seed offsets: constructor ops, args, union endpoints, enabled, query, commands, tag
PARTS={'ops':(0,8,(4,2)), 'args':(8,88,(4,2,10)), 'union':(88,104,(2,8)),
       'on':(104,105,(1,)), 'query':(105,121,(2,8)), 'commands':(121,135,(2,7)),
       'payload':(135,139,(4,))}
