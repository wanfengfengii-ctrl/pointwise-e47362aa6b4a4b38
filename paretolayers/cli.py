"""Command line interface: verification, layering demo and benchmarks.

Run from the repository root, either ``python3 run.py <command>`` or
``python3 -m paretolayers <command>``.
"""

import argparse
import json
import os
import random
import subprocess
import sys
import threading
import time

from . import layers, layers_with_stats

EXIT_OK = 0
EXIT_FAIL = 1


def _dominates(a, b):
    """Independent, explicit definition: a <= b everywhere, < somewhere."""
    smaller = False
    for k in range(3):
        if a[k] > b[k]:
            return False
        if a[k] < b[k]:
            smaller = True
    return smaller


def brute_layers(records):
    """Reference implementation: pairwise dominance graph + longest path.

    Deliberately naive and independent from the production algorithm.  It
    compares every ordered pair directly (O(n^2) comparisons) and memoises
    the longest dominating chain per record.
    """
    n = len(records)
    dominators = [[] for _ in range(n)]
    for j in range(n):
        for i in range(n):
            if i != j and _dominates(records[i], records[j]):
                dominators[j].append(i)

    memo = {}

    def layer(i):
        if i not in memo:
            best = -1
            for p in dominators[i]:
                value = layer(p)
                if value > best:
                    best = value
            memo[i] = 0 if best < 0 else best + 1
        return memo[i]

    return [layer(i) for i in range(n)]


def _describe(value):
    return repr(value)


class _Checker:
    def __init__(self):
        self.cases = 0
        self.failures = []

    def expect(self, name, records, expected):
        self.cases += 1
        got = layers(records)
        if got != expected:
            self.failures.append(
                "%s: records=%s expected=%s got=%s"
                % (name, _describe(records), _describe(expected), _describe(got))
            )

    def compare_with_brute(self, name, records):
        self.cases += 1
        got = layers(records)
        expected = brute_layers(records)
        if got != expected:
            self.failures.append(
                "%s: records=%s brute=%s got=%s"
                % (name, _describe(records), _describe(expected), _describe(got))
            )

    def check(self, name, condition, detail=""):
        self.cases += 1
        if not condition:
            self.failures.append("%s: %s" % (name, detail))

    def report(self, stream=sys.stdout):
        print("checks run: %d" % self.cases, file=stream)
        if self.failures:
            for failure in self.failures:
                print("FAIL " + failure, file=stream)
            print("VERIFY: FAIL (%d failure(s))" % len(self.failures), file=stream)
            return EXIT_FAIL
        print("VERIFY: PASS", file=stream)
        return EXIT_OK


def _permutation_case(checker, records, name):
    """Reordering must move the layers along with the records."""
    base = layers(records)
    n = len(records)
    for seed in (1, 2, 3):
        positions = list(range(n))
        random.Random(seed).shuffle(positions)
        shuffled = [records[i] for i in positions]
        expected = [base[i] for i in positions]
        checker.expect("%s/reorder-%d" % (name, seed), shuffled, expected)


def run_verify(stream=sys.stdout):
    checker = _Checker()

    # The example from the specification.
    checker.expect(
        "spec-example",
        [(1, 1, 1), (1, 1, 1), (2, 1, 1), (1, 2, 0)],
        [0, 0, 1, 0],
    )

    # Exact duplicates: same layer, every copy reported.
    checker.expect(
        "duplicates",
        [(5, 5, 5), (5, 5, 5), (5, 5, 5), (4, 4, 4), (5, 5, 5)],
        [1, 1, 1, 0, 1],
    )
    checker.expect(
        "duplicates-negated",
        [(0, 0, 0), (0, 0, 0), (-1, 0, 0), (0, 0, 0), (0, 0, -1)],
        [1, 1, 0, 1, 0],
    )

    # Equality in a single coordinate must not block dominance: one coordinate
    # is constant, the other two rise together, so the records form a chain.
    checker.expect(
        "one-coordinate-equal-y",
        [(0, 3, 0), (1, 3, 1), (2, 3, 2), (3, 3, 3)],
        [0, 1, 2, 3],
    )
    checker.expect(
        "one-coordinate-equal-z",
        [(0, 0, 3), (1, 1, 3), (2, 2, 3), (3, 3, 3)],
        [0, 1, 2, 3],
    )
    checker.expect(
        "one-coordinate-equal-x",
        [(3, 0, 0), (3, 1, 0), (3, 2, 1), (3, 3, 2)],
        [0, 1, 2, 3],
    )
    # Equality in one coordinate with opposed movement: not comparable.
    checker.expect(
        "equal-y-antichain",
        [(0, 3, 9), (1, 3, 4), (2, 3, 1), (3, 3, 0)],
        [0, 0, 0, 0],
    )
    checker.expect(
        "equal-z-antichain",
        [(0, 9, 3), (1, 4, 3), (2, 1, 3), (3, 0, 3)],
        [0, 0, 0, 0],
    )
    # Same y and z, bigger x: dominance by the first coordinate alone.
    checker.expect(
        "x-only-dominance",
        [(0, 4, 4), (7, 4, 4), (1, 4, 4), (2, 4, 4)],
        [0, 3, 1, 2],
    )
    # Same two coordinates and one different: not comparable.
    checker.expect(
        "incomparable-shared-face",
        [(1, 2, 3), (2, 1, 3), (3, 2, 1)],
        [0, 0, 0],
    )

    # Negative coordinates.
    checker.expect(
        "negatives",
        [(-5, -5, -5), (-1, -1, -1), (-3, -3, -3), (-9, 0, 0)],
        [0, 2, 1, 0],
    )
    checker.expect(
        "negative-monotone-is-a-chain",
        [(-5, 5, 0), (-4, 6, 1), (-3, 7, 2)],
        [0, 1, 2],
    )
    checker.expect(
        "negative-antichain",
        [(-5, 5, 0), (-4, 4, -1), (-3, 3, -2)],
        [0, 0, 0],
    )

    # Full chain: every record dominates all earlier ones.
    chain = [(i, i, i) for i in range(12)]
    checker.expect("full-chain", chain, list(range(12)))
    descending_chain = [(11 - i, 11 - i, 11 - i) for i in range(12)]
    checker.expect("full-chain-reversed-input", descending_chain, list(range(11, -1, -1)))

    # Full antichain: increasing in one coordinate, decreasing in another.
    antichain = [(i, 11 - i, 0) for i in range(12)]
    checker.expect("full-antichain", antichain, [0] * 12)

    # Reordering (order invariance up to the induced permutation).
    for name, records in (
        ("reorder-spec-example", [(1, 1, 1), (1, 1, 1), (2, 1, 1), (1, 2, 0)]),
        ("reorder-mixed", [(3, 0, 9), (0, 0, 0), (3, 0, 9), (2, 5, -1), (0, 0, 1)]),
        ("reorder-negatives", [(-2, 4, 1), (-3, 4, 1), (-2, 4, 1), (-4, 0, 2)]),
    ):
        _permutation_case(checker, records, name)

    # Input must not be mutated, and layers_with_stats must agree with layers.
    original = [(1, 1, 1), (1, 1, 1), (2, 1, 1), (1, 2, 0), (-4, 2, 7)]
    snapshot = list(original)
    result = layers(original)
    checker.check("input-not-mutated", original == snapshot,
                  "input changed: %r" % (original,))
    checker.check("duplicate-positions-preserved", len(result) == len(snapshot),
                  "output length %d" % len(result))
    with_stats, stats = layers_with_stats(original)
    checker.check("stats-agree", with_stats == result,
                  "%r vs %r" % (with_stats, result))
    checker.check("stats-cover-records", stats["records"] == len(original),
                  "records=%r" % (stats["records"],))
    checker.check("empty-input", layers([]) == [], "layers([]) was not empty")
    checker.check("empty-stats", layers_with_stats([])[1]["records"] == 0,
                  "stats for [] not zeroed")

    # Randomized cross-check against the independent pairwise reference.
    rng = random.Random(20240517)
    for trial in range(120):
        n = rng.randrange(1, 8)
        coords = rng.choice((2, 3, 6))
        records = [
            (rng.randint(-coords, coords), rng.randint(-coords, coords),
             rng.randint(-coords, coords))
            for _ in range(n)
        ]
        checker.compare_with_brute("random-%d" % trial, records)

    # Denser random cases with deliberate duplicates.
    for trial in range(30):
        n = rng.randrange(4, 10)
        pool = [
            (rng.randint(-1, 1), rng.randint(-1, 1), rng.randint(-1, 1))
            for _ in range(3)
        ]
        records = [rng.choice(pool) for _ in range(n)]
        checker.compare_with_brute("random-duplicates-%d" % trial, records)

    # A medium-size case against the pairwise reference.
    medium = [(rng.randint(-3, 3), rng.randint(-3, 3), rng.randint(-3, 3))
              for _ in range(60)]
    checker.compare_with_brute("random-medium", medium)

    # Wide magnitudes must not overflow or lose ordering.
    big = 10 ** 30
    checker.compare_with_brute(
        "wide-magnitudes",
        [(big, -big, 0), (big, -big, 0), (big + 1, -big, 0),
         (-big, big, 0), (-big, big - 1, -1)],
    )

    # Exhaustive over every 3-record list drawn from a 3x3x3 grid with
    # negatives: 27^3 = 19,683 inputs, each checked against the pairwise
    # reference.  This is the strongest coverage of the sweep/index interplay
    # (duplicates, shared coordinates and incomparability all occur).
    grid = [(x, y, z) for x in (-1, 0, 1) for y in (-1, 0, 1)
            for z in (-1, 0, 1)]
    exhaustive_failures = 0
    for a in grid:
        for b in grid:
            for c in grid:
                records = [a, b, c]
                if layers(records) != brute_layers(records):
                    exhaustive_failures += 1
    checker.check("exhaustive-grid-3-records", exhaustive_failures == 0,
                  "%d of 19683 inputs disagreed" % exhaustive_failures)

    return checker.report(stream)


def run_demo(stream=sys.stdout):
    records = [
        (4, 2, 7),    # source A
        (4, 2, 7),    # source B: duplicate of A, same layer, kept
        (-1, 5, 0),   # negative coordinate
        (2, 2, 3),
        (0, 5, 3),
        (2, 2, 7),
        (4, 3, 3),
        (2, 6, 2),
        (0, 1, 1),
        (0, 1, 1),    # another duplicate
    ]
    result = layers(records)
    stats = layers_with_stats(records)[1]

    print("Pareto layering of multi-source records (smaller is better)")
    print("dominance: a <= b in every coordinate and < in at least one")
    print()
    print("  idx  record          layer")
    print("  ---  --------------  -----")
    for i, (record, layer) in enumerate(zip(records, result)):
        print("  %3d  %-14s  %5d" % (i, str(record), layer))
    print()

    width = max(result) + 1
    for layer in range(width):
        members = [i for i, value in enumerate(result) if value == layer]
        print("layer %d (%d record(s)):" % (layer, len(members)))
        for i in members:
            print("    #%-3d %s" % (i, records[i]))
    print()

    # Show a few direct comparisons that explain the layers: each record with
    # layer > 0 is paired with a dominator at exactly layer - 1.
    print("directly verified comparisons (a dominator at layer - 1):")
    shown = 0
    for j in range(len(records)):
        if result[j] == 0:
            continue
        for i in range(len(records)):
            if i != j and _dominates(records[i], records[j]) \
                    and result[i] + 1 == result[j]:
                print("    #%d %s dominates #%d %s  (%d + 1 = %d)"
                      % (i, records[i], j, records[j], result[i], result[j]))
                shown += 1
                break
        if shown >= 5:
            break
    if shown == 0:
        print("    (no non-zero layers in this sample)")
    print()

    seen = {}
    duplicate_groups = []
    for i, record in enumerate(records):
        if record in seen:
            duplicate_groups.append((seen[record], i, result[i]))
        else:
            seen[record] = i
    if duplicate_groups:
        for first, second, layer in duplicate_groups:
            print("duplicates: #%d and #%d are equal, both layer %d, each "
                  "reported." % (first, second, layer))
    else:
        print("duplicates: none in this sample.")
    print("index operations: %d query steps, %d update steps, %d writes, "
          "%d bisects, %d index cells"
          % (stats["query_steps"], stats["update_steps"],
             stats["update_writes"], stats["bisects"], stats["index_cells"]))
    return EXIT_OK


# ---------------------------------------------------------------- benchmarks

def _gen_random(n, rng):
    span = 10 ** 6
    return [(rng.randrange(-span, span), rng.randrange(-span, span),
             rng.randrange(-span, span)) for _ in range(n)]


def _gen_hotspot(n, rng):
    """Duplicates dominate: 70% of records come from a tiny pool."""
    hot = [(0, 0, 0), (1, 1, 1), (2, 2, 0), (-1, 3, 2), (5, 5, 5),
           (1, 0, 4), (0, 2, 2), (-2, -2, -2)]
    records = [hot[rng.randrange(len(hot))] for _ in range((n * 7) // 10)]
    records.extend(_gen_random(n - len(records), rng))
    rng.shuffle(records)
    return records


def _gen_chain(n, rng):
    """Every record dominates all earlier ones: the longest possible chain."""
    return [(i, i, i) for i in range(n)]


_PAGE_MIB = os.sysconf("SC_PAGE_SIZE") / (1024.0 * 1024.0)


def _resident_mib():
    """Current resident set size of this process, in MiB."""
    with open("/proc/self/statm", "r") as handle:
        pages = int(handle.read().split()[1])
    return pages * _PAGE_MIB


class _RssSampler(threading.Thread):
    """Sample process RSS in the background and remember the peak.

    ``tracemalloc`` would hook every allocation and slow the measured code by
    almost two orders of magnitude, so peak memory is taken from the kernel's
    resident set size instead.  The sampler costs one small file read per
    interval and runs on a separate thread that only gets scheduled between
    bytecodes of the measured work.
    """

    def __init__(self, interval=0.001):
        super().__init__(daemon=True)
        self.interval = interval
        self.peak = 0.0
        self._stopping = threading.Event()
        self._error = None

    def note(self):
        """Take a synchronous sample on the calling thread."""
        value = _resident_mib()
        if value > self.peak:
            self.peak = value

    def run(self):
        try:
            while not self._stopping.is_set():
                self.note()
                self._stopping.wait(self.interval)
        except Exception as exc:  # pragma: no cover - defensive
            self._error = exc

    def stop(self):
        self._stopping.set()
        self.join()
        if self._error is not None:
            raise self._error


def _measure_one(distribution, size, seed):
    """Measure one case in this process; used by the child process below.

    Total peak RSS covers the input records plus the auxiliary index; the
    incremental figures subtract the RSS just before ``layers`` is entered,
    isolating the algorithm's own working set.
    """
    sampler = _RssSampler()
    sampler.start()
    rng = random.Random(seed + size + len(distribution))
    records = _GENERATORS[distribution](size, rng)
    sampler.note()  # include record generation in the peak
    baseline = _resident_mib()
    start = time.perf_counter()
    result, stats = layers_with_stats(records)
    elapsed = time.perf_counter() - start
    sampler.note()  # a run shorter than the sampling interval still counts
    sampler.stop()
    total_peak = sampler.peak

    return {
        "distribution": distribution,
        "records": len(records),
        "seconds": elapsed,
        "peak_mib": total_peak,
        "aux_peak_mib": max(0.0, total_peak - baseline),
        "bytes_per_record": total_peak * 1024.0 * 1024.0 / max(1, len(records)),
        "max_layer": max(result) if result else 0,
        "groups": stats["groups"],
        "query_outer_visits": stats["query_outer_visits"],
        "query_steps": stats["query_steps"],
        "update_outer_visits": stats["update_outer_visits"],
        "update_steps": stats["update_steps"],
        "index_ops": stats["query_steps"] + stats["update_steps"],
        "update_writes": stats["update_writes"],
        "bisects": stats["bisects"],
        "index_cells": stats["index_cells"],
    }


GENERATORS = ("random", "hotspot", "chain")

_GENERATORS = {
    "random": _gen_random,
    "hotspot": _gen_hotspot,
    "chain": _gen_chain,
}

def _measure_in_child(distribution, size, seed):
    """Run one case in a fresh interpreter so RSS peaks are not carried over.

    The parent cannot see the child's heap directly, so the child samples its
    own RSS from before record generation until the layering call returns,
    which covers both the input and the auxiliary index.
    """
    payload = json.dumps({
        "distribution": distribution,
        "size": size,
        "seed": seed,
    })
    package_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    completed = subprocess.run(
        [sys.executable, "-m", "paretolayers", "--measure", payload],
        capture_output=True,
        text=True,
        check=False,
        cwd=package_root,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "measurement child failed (%d): %s"
            % (completed.returncode, completed.stderr.strip())
        )
    return json.loads(completed.stdout.strip().splitlines()[-1])


def run_bench(sizes, distributions, seed=12345, repeats=1, stream=sys.stdout):
    """Measure every (distribution, size) in a fresh child and print a table.

    With ``repeats > 1`` the fastest run is reported, which is the most stable
    statistic on a shared machine.
    """
    rows = []
    header = ("distribution  records    seconds   peak MiB  aux MiB  "
              "max layer   query ops   update ops  writes  bisects  cells")
    print(header, file=stream)
    print("-" * len(header), file=stream)
    for distribution in distributions:
        for size in sizes:
            best = None
            for _ in range(repeats):
                row = _measure_in_child(distribution, size, seed)
                if best is None or row["seconds"] < best["seconds"]:
                    best = row
            rows.append(best)
            print("%-12s  %7d  %9.3f  %9.2f  %7.2f  %9d  %10d  %11d  %6d  "
                  "%7d  %5d"
                  % (best["distribution"], best["records"], best["seconds"],
                     best["peak_mib"], best["aux_peak_mib"], best["max_layer"],
                     best["query_steps"], best["update_steps"],
                     best["update_writes"], best["bisects"],
                     best["index_cells"]),
                  file=stream)
            stream.flush()
    return rows


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["--measure"]:
        payload = json.loads(argv[1])
        row = _measure_one(payload["distribution"], payload["size"],
                           payload["seed"])
        print(json.dumps(row))
        return EXIT_OK

    parser = argparse.ArgumentParser(
        prog="paretolayers",
        description="Pareto layering for 3-D records (stdlib only).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("verify", help="cross-check against an independent pairwise reference")

    sub.add_parser("demo", help="print a layering demonstration")

    bench = sub.add_parser("bench", help="time and profile doubling sizes")
    bench.add_argument("--sizes", type=int, nargs="+",
                       default=[100000, 200000, 400000],
                       help="record counts (default: 100000 200000 400000)")
    bench.add_argument("--distributions", nargs="+",
                       default=["random", "hotspot", "chain"],
                       choices=["random", "hotspot", "chain"],
                       help="workload shapes (default: all three)")
    bench.add_argument("--json", action="store_true",
                       help="print machine-readable results as well")
    bench.add_argument("--repeats", type=int, default=1,
                       help="runs per case; the fastest is reported (default: 1)")

    args = parser.parse_args(argv)

    if args.command == "verify":
        return run_verify()
    if args.command == "demo":
        return run_demo()
    if args.command == "bench":
        rows = run_bench(args.sizes, args.distributions,
                         repeats=max(1, args.repeats))
        if args.json:
            print(json.dumps(rows, indent=2))
        return EXIT_OK
    return EXIT_FAIL


if __name__ == "__main__":
    sys.exit(main())
