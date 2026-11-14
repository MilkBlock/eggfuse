# Fixed nonlinear width experiment

This is the selected three-rule Python/MLX GPU prototype, not the egglog runtime
or the full Eggcc pipeline. No backpropagation or real-run training was used.

The active model's actual GCD/LCM feedback captures contain 12 incorrect
completion partitions in 140 admitted instances. Eleven are rule 290, including
nine direct-source instances. Thus generated-source error accumulation alone
does not account for the remaining failures. This audit concerns predicted Eq
partitions; exact graph acceptance is a different check.

Keep the same 641 synthetic training entries, inputs, ridge regularization and
fixed random seed, and try `--normalized-joint --normalized-width 1024` instead
of the default 256. The persisted projection determines GPU matrix shapes;
there is no new device branch, lookup or backpropagation. Changing width also
changes the sampled matrix; this is not a nested-basis isolation experiment.

| Fixed captured development inputs | 256 columns | 1024 columns |
|---|---:|---:|
| GCD whole partition | 36/41 | 34/41 |
| GCD direct source | 23/26 | 20/26 |
| LCM whole partition | 93/99 | 84/99 |
| LCM direct source | 72/78 | 64/78 |

The trial passed CPU/GPU numerical parity but regressed prediction. It is
rejected; the existing active head is unchanged. No new feedback rollout or
speed measurement was run for the rejected head. The feature projection plus
center grows from 7,503,372 to 29,925,900 stored bytes. This does not prove that
all larger bases fail, nor that the current features cannot represent the target.

`normalized-width-results.json` records the artifact archive, checksums and
results. The archive includes the exact training argv, report, weights and log.
`test_normalized_joint.py` checks configurable width, invalid dimensions and
actual MLX score parity. The default 256-column path remains unchanged.

The interaction enumerator still bounds producer count and class count and
assigns one common matched/completed phase to all producers. Its completeness
flag is not a claim of coverage of mixed phases, all rulesets or iterative closure.
Next investigate the structural and scalar context of rule 290 failures before
increasing model size again.
