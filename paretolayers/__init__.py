"""Pareto layers for 3-dimensional integer records (standard library only).

``layers(records)`` returns, in input order, the Pareto layer of each record.

Dominance
---------
``a`` dominates ``b`` iff ``a[i] <= b[i]`` for every coordinate and
``a[i] < b[i]`` for at least one.  The layer of a record is ``0`` when nothing
dominates it and otherwise ``1 + max(layer(p) for p dominating it)``.
Exact duplicates are mutually incomparable, so they share a layer and are
each kept in the output.

Algorithm
---------
Layers are ranks in the strict product order, so they satisfy

    layer(q) = max({0} | {layer(p) + 1 : p < q})

with ``p < q`` the dominance relation.  Every dominator of ``q`` has a first
coordinate ``<= q[0]``, and one that shares ``q[0]`` must be strictly smaller
in one of the remaining coordinates, hence appears earlier when the records
are sorted lexicographically by ``(x, y, z)``.  Exact duplicates are the only
earlier records that are equal in all three coordinates.

Therefore one lexicographic sweep suffices.  Before inserting a group of
identical records, a 2-D prefix-maximum query over ``(y <= q.y, z <= q.z)``
returns the largest stored value ``layer(p) + 1`` among all dominators;
inserting after the whole group keeps duplicates from dominating each other.
Stored values are shifted by one so that ``0`` unambiguously means "no
dominator".

The index is a Fenwick tree over compressed ``y`` whose cells each hold a
Fenwick prefix-max tree over the ``z`` values that can reach that cell.  The
inner coordinate lists are built offline from the distinct records, so the
index is plain integer arrays searched with ``bisect``; updates and queries
both cost ``O(log m)`` outer cells times ``O(log n)`` inner steps.  Each
distinct record is inserted once, all copies are written to the output, nothing
is re-scanned per layer, and no pair of records is ever compared directly.

Complexity
----------
Let ``n`` be the number of records and ``m <= n`` the number of distinct
``y`` values.

* Time: ``O(n log n)`` for the sort plus ``O(n log m log n)`` for the sweep,
  i.e. ``O(n log^2(n + 2))``.
* Auxiliary space: the offline index holds ``O(n log m)`` cells, i.e.
  ``O(n log(n + 2))``; the output and a few ``O(n)`` bookkeeping arrays come
  on top.

The index operation counters exposed by :func:`layers_with_stats` make the
query/update work explicit for benchmarking.
"""

from bisect import bisect_left, bisect_right

__all__ = ["layers", "layers_with_stats"]


def layers(records):
    """Return the Pareto layer of every record, in input order.

    ``records`` is a list of integer triples (booleans are excluded by the
    contract).  The input is never modified and duplicate records are kept.
    """
    return _compute(records)[0]


def layers_with_stats(records):
    """Like :func:`layers`, but also return a dict of index-operation counts.

    The counters describe the Fenwick index only: inner-tree steps, outer-cell
    visits, actual tree writes and coordinate bisections.  They are meant for measurement and testing, not
    as part of the layering result.
    """
    return _compute(records)


def _compute(records):
    n = len(records)
    stats = {
        "records": n,
        "groups": 0,
        "query_outer_visits": 0,
        "query_steps": 0,
        "update_outer_visits": 0,
        "update_steps": 0,
        "update_writes": 0,
        "bisects": 0,
        "index_cells": 0,
    }
    if n == 0:
        return [], stats

    # Lexicographic order: every dominator precedes its dominated records.
    order = sorted(range(n), key=records.__getitem__)

    # Compress y.  z values are used verbatim; the per-cell sorted lists make
    # prefix search on them exact.
    ys = sorted({records[i][1] for i in range(n)})
    m = len(ys)

    # Identical records form one group; the index needs one insertion each.
    groups = []
    start = 0
    while start < n:
        first = records[order[start]]
        end = start + 1
        while end < n and records[order[end]] == first:
            end += 1
        groups.append((start, end, bisect_left(ys, first[1]) + 1, first[2]))
        start = end
    stats["groups"] = len(groups)

    # Offline index layout: which z values can ever update each outer cell.
    cell_keys = [[] for _ in range(m + 1)]
    for _start, _end, ry, z in groups:
        i = ry
        while i <= m:
            cell_keys[i].append(z)
            i += i & -i
    cell_trees = [None] * (m + 1)
    for i in range(1, m + 1):
        keys = cell_keys[i]
        if keys:
            keys = sorted(set(keys))
            cell_keys[i] = keys
            cell_trees[i] = [0] * (len(keys) + 1)
            stats["index_cells"] += len(keys)

    result = [0] * n
    q_outer = q_steps = u_outer = u_steps = writes = bisects = 0

    for start, end, ry, z in groups:
        # 2-D prefix maximum over y <= ry and z <= z.  Values are layer+1.
        best = 0
        i = ry
        while i:
            keys = cell_keys[i]
            bisects += 1
            p = bisect_right(keys, z)
            tree = cell_trees[i]
            q_outer += 1
            while p:
                value = tree[p]
                if value > best:
                    best = value
                p -= p & -p
                q_steps += 1
            i -= i & -i

        # best == 0 means "no dominator" and yields layer 0.
        layer = best
        for t in range(start, end):
            result[order[t]] = layer

        # One insertion per identical-record group: all copies share (y, z)
        # and the layer, and they must not dominate each other.
        value = layer + 1
        i = ry
        while i <= m:
            keys = cell_keys[i]
            bisects += 1
            p = bisect_left(keys, z) + 1
            tree = cell_trees[i]
            limit = len(tree)
            u_outer += 1
            while p < limit:
                if value > tree[p]:
                    tree[p] = value
                    writes += 1
                p += p & -p
                u_steps += 1
            i += i & -i

    stats["query_outer_visits"] = q_outer
    stats["query_steps"] = q_steps
    stats["update_outer_visits"] = u_outer
    stats["update_steps"] = u_steps
    stats["update_writes"] = writes
    stats["bisects"] = bisects
    return result, stats
