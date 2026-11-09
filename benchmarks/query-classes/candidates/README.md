# Reproducible intermediate candidates

Both patches apply to clean commit `86800d89` and contain the runtime/compiler
sources and regressions, including new files. They were checked with a separate
temporary Git index using `git apply --cached --check`. Build the runtime package
alone with `sparse-cells,view-ports,storage-metrics`; do not unify compiler
dependencies into the normal benchmark build.

- `first.patch`: the first simple class-range implementation, receipt-demand
  pruning and report timer. It retains the old linear report membership check.
  See the parent directory's first four-lane campaign.
- `adaptive.patch`: bounded four-key lookahead, local counter accumulation and
  indexed report membership. This is a **withdrawn** runtime candidate. The
  inference result did not justify retaining the extra traversal state. Its
  report membership fix is retained independently in the final implementation.
  See `../adaptive/` for actual timings and costs.

The final retained source is in the repository, not another patch: simple class
ranges and checked future-use certificates, receiver-driven receipt demand,
and indexed report membership. Full validation and timing are in `../final/`.
These experiments are standalone Cell CPU code, not changes to native egglog.
