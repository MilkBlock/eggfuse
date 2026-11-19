# Figure 07: global finish barrier and local private readiness

Compare identical source rules, immutable monotone facts, input events and public
Run boundaries. The producer relations are P0(k,x), P1(k,y) and U(k,z). C requires
both P0 and P1 at the SAME key, V uses only U. Three producer Runs expose three
separate event waves. The final consumer Run opens the public view. Private
evaluation in the local arm may happen after a completed producer wave, but the
public C/V view must remain closed until finish. This does not authorize early
publication, reordering of noncommutative writes, or general negative reasoning.

Primary schedules: (a) compute both consumers only at finish and (b) compute
each eligible consumer at its first observed ready tick and retain actual RHS
rows and parent witness handles. Both must publish exactly the source facts at
the source finish boundary. Record actual evaluation time for each candidate,
missing-parent reads, duplicate evaluation/commit, late private work, private
work never published, impossible/pending reads at seal, each public snapshot
and final graph. The obligation set follows observed anchors/stream semantics;
no empty neural output certifies saturation. Repeated source events are legal
and cannot cause repeated logical effects. Exact scheduler runs on the GPU,
without knowing future waves or asking CPU for a ready mask.

Secondary learned controls: train two small PyTorch predictors at seeds
1703/1709 on the same training streams, final checkpoints only. The keyed
predictor sees raw event key/type/value. A matched key-blind predictor has
its input event-key content zeroed, but retains kind/value, time, candidate
query keys and all other features. Fit cumulative eligibility per consumer and
candidate key with supervised BCE, 768 Adam steps at 0.002, batch 32, alternating
training graph samples with identical per-seed graph indices. Four ticks include
finish; finish adds no new facts. During inference proposals are produced
incrementally, input by input, on the GPU from the current wave and retained
past state. Ground truth, seals and complete source relations are not predictor
inputs. Exact dependency checks are a separate scheduler arm. Fix threshold .5.

Compare raw proposal diagnostic, exact guard on proposals, and guard with an
exact final drain if a legitimate private result was missed. The last can
guarantee completion by construction and must disclose added finish work.
Time exact and combined learned execution from raw integer inputs to final
synchronized output (trace=False). Measure four full public snapshots and
private proof/witness timing separately, verify actual values and distinct
writes versus a CPU source oracle, and preferably also actual Rust Cell CPU
exports. Examine paired early/late/missing cases with unchanged U chain
and wrong-key facts of identical value. Report cold versus warm boundaries
where relevant and distinguish online critical-path offsets from device time.
The learned arms use identical parameter count/optimizer, one shared event
matching function and an order-invariant max over seen event evidence.
