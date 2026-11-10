#!/usr/bin/env python3
"""Generate a bounded Cell query fixture with mutable, union and late-input Runs."""
import argparse
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('output', type=Path)
a = p.parse_args()
source = '''(datatype E (Leaf i64) (Wrap E))
(function Start (E) i64 :merge (max old new))
(function Cost (E) i64 :merge (max old new))
(function Limit (E) i64 :merge (max old new))
(function Out (E) i64 :merge (max old new))
(function Link (E) E :merge old)
(function PairCost (E i64) i64 :merge (max old new))
(function Echo (E) i64 :merge (max old new))
(ruleset see)
(ruleset grow)
(rule ((= s (Start x))) ((Wrap x)) :ruleset grow)
(rule ((= p (Wrap x)) (= c (Cost x))) ((set (Cost p) (+ c 0))) :ruleset see :name "neighbor-point")
(rule ((= s (Start x)) (= c (Cost x)) (= l (Limit x))
       (= v (+ c s)) (< v l))
      ((set (Out x) v)) :ruleset see :name "point-continuation")
(rule ((= s (Start x)) (= y (Link x)) (= v (PairCost y s)) (= checked (+ v 0))
       (= checked (Cost y)))
      ((set (Echo x) checked)) :ruleset see :name "eq-result-and-composite-key")
'''
for i in range(128):
    # Missing Limit exercises a failed lookup; some guards fail as well.
    cost = i if i != 127 else 9223372036854775807
    source += f'(set (Cost (Leaf {i})) {cost})\n'
    source += f'(set (PairCost (Leaf {i}) 1) {cost})\n'
    source += f'(set (Link (Leaf {i})) (Leaf {(i + 1) % 128}))\n'
    if i % 7:
        source += f'(set (Limit (Leaf {i})) {i + (1 if i % 5 == 0 else 10)})\n'
    source += f'(set (Start (Leaf {i})) 1)\n'
source += '''(ruleset change) (ruleset absent) (ruleset restore)
(rule ((= s (Start (Leaf 0))))
      ((set (Limit (Leaf 0)) 20) (set (Cost (Leaf 1)) 3)
       (delete (Cost (Leaf 2)))) :ruleset change)
(rule ((= s (Start (Leaf 0)))) ((set (Start (Leaf 2)) 2)) :ruleset absent)
(rule ((= s (Start (Leaf 0))))
      ((set (Cost (Leaf 2)) 4) (union (Leaf 3) (Leaf 4))) :ruleset restore)
(run-schedule (seq (run grow) (run see) (run change) (run see) (run absent) (run see)
                   (run restore) (run see) (run see)))
(check (= (Out (Leaf 0)) 1) (= (Out (Leaf 1)) 4) (= (Out (Leaf 2)) 6))
'''
a.output.parent.mkdir(parents=True, exist_ok=True)
a.output.write_text(source)
