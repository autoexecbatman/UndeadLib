# Dijkstra map - contract

**Spec of the spec.** This contract answers one question: what a caller hands the
library and what comes back, at the C++ layer and at the C layer, such that
C++RogueLike's flood (eight-way, step costs 1 and 2, flooded from a goal) and a
Python caller can both use it without a call crossing the C boundary. It is the
wrong contract if the game's flood cannot be expressed through it, or if a C
caller needs a function pointer.

## Ownership and boundaries

- **The C++ core owns the algorithm.** `include/undead/` is header-only. The C
  shim (`src/undead_c.cpp`) calls the core and holds no search logic of its own.
- **A node is a `size_t` index** in `[0, node_count)`. A grid cell is
  `row * width + column`. Distances come back indexed the same way, so a caller's
  flat array (a C array, a numpy array) lines up with them.
- **The graph owns its shape.** The core asks a graph only `node_count()` and
  `for_each_neighbour(node, visit)`, where `visit(next, stepCost)` is called once
  per edge. Portals, corner-cutting rules and one-way edges live in the graph.
- **`GridGraph` is the ready-made graph** over a `uint8_t` step-cost array: the
  cost of an edge is the cost of the cell it enters, and a cost of 0 means the
  cell cannot be entered. It views the caller's array and copies nothing.
- **A source has distance 0 whatever its own cost**, so a flood may start from a
  cell nothing can enter (a goal on a shut door).
- **Absence is `std::optional` in C++ and `UNDEAD_UNREACHED` (UINT32_MAX) in C.**
  The sentinel exists only at the C boundary, where there is no optional.
- **Errors: exceptions in C++, an `int` status in C.** No exception crosses the C
  boundary. On any error the C output array is not written.

## Algorithm

Dial's algorithm: Dijkstra with a circular bucket queue of `maxStepCost + 1`
buckets, valid for integer step costs in `[0, maxStepCost]`. A binary-heap
variant for unbounded costs is not built; it waits for a caller whose costs do
not fit in buckets.

## Claims and the check that catches each one

| Claim | Check |
|---|---|
| Distances equal shortest-path distances | Random grids and random graphs, fixed seeds, compared against a Bellman-Ford oracle in the tests that enumerates neighbours itself, not through `GridGraph` |
| The game's door pricing is expressible | Hand-derived corridor case with a cost-2 cell |
| Four-way and eight-way differ only in diagonals | Hand-derived 3x3 corner case |
| Sources get 0, including on a cost-0 cell | Hand-derived case |
| Zero-cost edges (portals) work | Generic graph case |
| Bad input is refused: grid size mismatch, source out of range, neighbour out of range, step cost above the bound, distance overflow | One test per refusal, each reading the exception type |
| C status codes map one-to-one to those refusals, and the output is untouched on error | One C API test per code, output pre-filled and compared after |
| `undead.h` is valid C | A `.c` file in the test target includes it and calls the function; the test calls that C function |

## Resources

- Distance map: 4 bytes per node.
- Bucket queue: `maxStepCost + 1` vectors, plus at most one entry per edge
  relaxation in flight. `GridGraph` bounds `maxStepCost` at 255.
- Time: each node is settled once, each edge relaxed at most once per settle,
  and the scan visits one bucket per distance value up to the largest finite
  distance D. **D is the term that dominates when costs are large**: a chain
  reaching D of about 2^32 took 2.1 s in Release and 20 s in Debug, measured
  2026-10-31. For game grids with costs 1 and 2, D is at most twice the cell
  count. A caller with large costs and sparse distances wants the deferred
  binary-heap variant.

## Decisions made while building

- **`GridGraph::cell_count` is the one place `width * height` is computed and
  checked for overflow**; the constructor and the C shim both call it.
- **A duplicate source is queued twice rather than guarded.** The guard was an
  equivalent mutant: the second entry relaxes to the same distances.
- **The stale-entry check (`distances[node] != current`) cannot change a
  result**, only the work done: a stale entry relaxes from a distance larger
  than its node's true one, so it can lower nothing. It is kept for speed, and
  no output test can kill a mutant of it.
- **Refused where `size_t` is 32 bits: `maxStepCost + 1` buckets that do not fit**
  (`std::length_error`). Untested here: the condition is false on every 64-bit
  build, and the wasm32 target has not been built.
- **Untested boundary: a distance of exactly `UINT32_MAX - 1` is kept.** Reaching
  it needs 4294967294 = 2 x 2147483647 (prime), so either a step cost near
  2^31, which is 48 GiB of buckets, or about 2^31 nodes. The `UINT32_MAX`
  refusal itself is tested.
