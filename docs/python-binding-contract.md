# Python binding - contract

**Spec of the spec.** This contract answers what a Python caller hands
`undead_dijkstra_map` and gets back, such that no value reaches C that C would
misread. It is the wrong contract if a Python value can wrap, overrun or
dangle on its way into C, or if the binding holds any search logic.

## Ownership and boundaries

- **The C API owns the algorithm and its refusals.** The binding converts
  arguments, calls `undead_c`, and turns each status into an exception.
- **The caller names the DLL.** `UndeadLibrary(dll_path)` loads it; importing
  the module loads nothing and holds no state.
- **The binding checks what C cannot see**, before calling:
  - `width`, `height` and every source are non-negative, since ctypes wraps a
    negative `size_t` silently;
  - `step_costs` is a buffer of unsigned bytes (`bytes`, `bytearray`, a numpy
    `uint8` array) whose length is exactly `width * height`.
- **Distances come back as `list[int | None]`**, `None` where no source
  reaches, indexed `row * width + column`.

## Status to exception

| C status | Python |
|---|---|
| `UNDEAD_ERROR_GRID_SIZE` | `ValueError` |
| `UNDEAD_ERROR_SOURCE_OUT_OF_RANGE` | `IndexError` |
| `UNDEAD_ERROR_CONNECTIVITY` | `ValueError` |
| `UNDEAD_ERROR_DISTANCE_OVERFLOW` | `OverflowError` |
| `UNDEAD_ERROR_OUT_OF_MEMORY` | `MemoryError` |
| `UNDEAD_ERROR_NULL_ARGUMENT`, `UNDEAD_ERROR_INTERNAL`, unknown | `RuntimeError` - a binding or library defect |

## Claims and the check that catches each one

| Claim | Check |
|---|---|
| Distances are shortest paths | Random grids, fixed seeds, against a Bellman-Ford oracle in the tests |
| The game's corridor floods as in C | Hand-derived door corridor |
| `bytes`, `bytearray` and numpy `uint8` all work | One test each |
| Wrong-length costs, a wrong element type, negative sizes and negative sources are refused before C | One test each, reading the exception type |
| Every status maps to its exception | One test per reachable status; the overflow test is the 16843010-cell corridor |
| The DLL path comes from CMake, not a literal | `ctest` runs pytest with `UNDEAD_C_DLL` set to `$<TARGET_FILE:undead_c>` |
