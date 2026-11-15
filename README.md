# Pareto layering for 3-D records

`paretolayers.layers(records)` takes a list of up to 100,000 integer triples
and returns each record's Pareto layer, in input order. Booleans are excluded
by the contract; negative coordinates are fully supported.

A record `a` **dominates** `b` iff `a[i] <= b[i]` for all three coordinates and
`a[i] < b[i]` for at least one. A record with no dominator is layer `0`; every
other record is `1 +` the largest layer among its dominators. Equal triples are
mutually incomparable, so duplicates share a layer and each copy is reported.

```python
>>> from paretolayers import layers
>>> layers([(1, 1, 1), (1, 1, 1), (2, 1, 1), (1, 2, 0)])
[0, 0, 1, 0]
```

The input is never modified; the output is a new list of the same length
(`[]` for empty input). Pure standard library.

## Status

Implemented, verified and benchmarked.

- `python3 run.py verify` — 184 independent checks, exit 0:
  pairwise reference on randomized cases, the specification example, duplicates,
  equality in one coordinate (both as a chain and as an antichain), negatives,
  a full 12-record chain (also fed in reverse), a full antichain, reorderings,
  input immutability, and agreement between `layers` and `layers_with_stats`.
  The reference implementation deliberately compares every ordered pair
  directly and walks the dominance graph, so it shares no logic with the
  production sweep. Included are all 19,683 three-record lists drawn from the
  27 points of the `{-1,0,1}³` grid, a `±10³⁰` case, and duplicate-heavy
  random inputs; `python3 -m unittest discover -s tests` runs a further 19
  tests (exhaustive 3-record grid, chain/antichain, stats and a no-pairwise
  operation-budget guard).
- `python3 run.py demo` — prints a ten-record layering: per-record table, layers
  as sets, representative dominance steps (`x + 1 = y`), duplicate handling, and
  index operation counts.
- `python3 run.py bench` — fresh-subprocess measurements per case.

`python3 -m paretolayers <cmd>` is equivalent when the repository root is on
`sys.path`; `run.py` is the form used by `.pointwise-runtime.json` because a
script's own directory is always importable.

No known defects. The five hand-written fixture expectations written first
were wrong (two "single-coordinate equality" examples were actually
antichains, one "negative antichain" was a monotone chain); the pairwise
reference confirmed the implementation in every case and the fixtures were
corrected. This is worth stating plainly because a wrong fixture is exactly
what an implementation bug looks like until it is cross-checked.

## Algorithm

Layers are ranks of the strict product order, so `layer(q) = 1 + max{layer(p)
: p dominates q}` with `0` for an empty set of dominators.

Every dominator of `q` has a first coordinate `<= q[0]`. If it shares that
coordinate it must be strictly smaller in another one, so it is still earlier
in a lexicographic sort by `(x, y, z)`. Sorting once therefore puts every
dominator before its dominated record; only exact duplicates are equal in all
coordinates.

One sweep over the sorted records then suffices. For a group of identical
records:

1. ask the index for the largest stored value over `y <= q.y, z <= q.z`
   (stored values are `layer + 1`, so `0` means "no dominator");
2. assign that value to every record in the group;
3. insert the group once with `layer + 1`.

Inserting after the whole group is what keeps duplicates from dominating each
other. Directional correctness of the query follows from the sweep: any
record already inserted with `y <= q.y` and `z <= q.z` is `<= q` in all
coordinates and is not an exact duplicate, so it dominates `q`. No pair of
records is ever examined.

### Index

A Fenwick tree over compressed `y` (size `m <= n`); each of its cells holds a
second Fenwick prefix-max tree over the compressed `z` values that can reach
that cell. The inner coordinate lists are built offline from the distinct
records, so the index is plain arrays and both operations are exact integer
lookups with `bisect`.

Both prefix queries and point updates are `O(log m)` outer cells times
`O(log n)` inner steps.

### Complexity

With `n` records and `m <= n` distinct `y` values:

| Resource | Bound | Who pays |
| --- | --- | --- |
| Time | `O(n log²(n+2))` | sort `O(n log n)` + one sweep with `O(log n)` Fenwick update/query pairs |
| Auxiliary space | `O(n log(n+2))` | offline index cells plus `O(n)` bookkeeping |
| Record-pair comparisons | none | quadrant queries, never pairwise |

There is no level-by-level rescan: each record is written once and each
distinct triple enters the index exactly once.

## Measurements

Machine: Linux 6.12 container, 10 cores, Python 3.11.2. Wall-clock time of
`layers` only (record generation and process start-up are excluded); peak
resident memory of a fresh child process, measured by a 1 ms `/proc/self/statm`
sampler. `aux MiB` is the peak after the records exist, i.e. the algorithm's
own working set. `query ops` / `update ops` are the inner Fenwick steps
summed, `writes` counts actual array stores, `bisects` the coordinate searches,
`cells` the offline `O(n log m)` index cells.

```
distribution  records    seconds   peak MiB  aux MiB  max layer   query ops   update ops  writes  bisects  cells
----------------------------------------------------------------------------------------------------------------
random         100000      3.369      77.32    50.95        104     3173352      4233165  2016285  1666676  850550
random         200000      9.534     145.45   103.00        130     7067106      9433898  4487275  3534191  1807579
random         400000     25.549     282.17   207.56        169    15656104     20961491  9807711  7481998  3832343
hotspot        100000      0.517      33.81    18.15         68      767712      1041053   512460   448798   229246
hotspot        200000      1.703      57.17    36.16         85     1747741      2331529  1136997   956387   487816
hotspot        400000      5.366     105.45    73.71        109     3940722      5210025  2511707  2034570  1038101
chain          100000      1.006      73.64    53.47      99999      815030      4499120  4499120  1693030   878000
chain          200000      2.188     136.49   106.30     199999     1730054      9976240  9976240  3586054  1856000
chain          400000      5.515     266.79   216.69     399999     3660102     22008480 22008480  7572102  3912000
```

Reproduce with `python3 run.py bench --sizes 100000 200000 400000 --repeats 2`
(`--json` for machine-readable rows). Each case runs in a fresh interpreter.
An earlier run of the same code came in 17–25% faster (400k: `random` 21.9 s,
`hotspot` 4.43 s, `chain` 4.40 s), so this shared container's wall clock has a
real run-to-run spread. The operation counts and memory figures are bit-identical
across runs because the algorithm is deterministic; those are the trustworthy
columns, and seconds should be read as indicative.

Scaling (400k / 100k, a 4× size increase), using the table above:

| Workload | Time | Index ops | Peak MiB | Reading |
| --- | --- | --- | --- | --- |
| `random` | 7.58× | 4.94× | 3.65× | ops grow ≈`n log²n`; time outruns ops by a constant factor per step |
| `hotspot` | 10.38× | 5.06× | 3.12× | same pattern, larger drift |
| `chain` | 5.48× | 4.83× | 3.62× | sequential index access: time tracks ops closely |

The operation counts are the honest complexity evidence: no hidden rescanning,
no pairwise work, and growth slightly above linear (`log` factors) as predicted.
Wall-clock grows faster than the op count on the random-access workloads
because the per-step cost itself drifts with footprint: timing the sweep alone
gives 230 → 280 ns per inner step for `random`-ordered points with a
three-value index, and 365 → 500 ns when the index spans millions of cells.
That is memory latency and allocation pressure, not extra asymptotic work.
`chain` touches the index sequentially, which keeps its ratio closest to the
op-count ratio.

Memory is linear in `n` once the fixed interpreter baseline is subtracted:
`aux MiB` steps 51.0 → 103.0 → 207.6 for `random`, i.e. about 0.52 MiB per
1,000 records, matching the `O(n log n)` cell count (the offline index holds
8.5 → 9.6 cells per record as `log n` grows). Per-record totals above include
the input list and interpreter; `bytes_per_record` falls toward ~0.7 KiB as
fixed costs amortise.

Operation counts at 100k (`random`): 3,173,352 query steps + 4,233,165 update
steps + 1,666,676 bisections for 100,000 records, i.e. ~90 index operations per
record, each inside a `log²` loop over an 850,550-cell index.

`hotspot` puts 70% of records into a pool of eight triples, so most groups are
exact duplicates and the input list shares those tuple objects (hence its small
`peak MiB`); `chain` is `(i, i, i)`, where every record dominates all earlier
ones and the maximum layer is `n - 1`; `random` spreads coordinates over
`[-10^6, 10^6)`.

At small sizes the fixed interpreter baseline dominates `peak MiB` (~10 MiB);
`aux MiB` stays proportional to the index:

```
distribution  records    seconds   peak MiB  aux MiB  max layer   query ops   update ops  writes  bisects  cells
----------------------------------------------------------------------------------------------------------------
random           1000      0.007      10.71     0.51         17       11716       16518    9107     9998   5060
random           5000      0.045      13.43     2.66         32       85606      132320   66622    63183  33369
random          10000      0.124      17.16     5.45         43      200629      309054  150030   136193  71559
chain            1000      0.005      10.60     0.45        999        4938       16518   16518     9998   5060
chain            5000      0.029      13.09     2.58       4999       29809      136390  136390    63173  33364
chain           10000      0.064      16.53     5.56       9999       64613      311144  311144   136341  71728
```

## Layout

```
run.py                     launcher: python3 run.py verify|demo|bench
paretolayers/__init__.py   layers / layers_with_stats implementation
paretolayers/cli.py        verify, demo, bench and the measurement child
paretolayers/__main__.py   python3 -m paretolayers
.pointwise-runtime.json    setup / verify / demo argv
```

`layers_with_stats(records)` returns `(layers, stats)` where `stats` counts
index operations and records; it is used by tests and benchmarks and is not
needed for normal use.
