# JavaScript binding - contract

**Spec of the spec.** This contract answers what a JavaScript caller, in a
browser or in Node, hands `undead_dijkstra_map` and gets back, such that no
value reaches the WebAssembly build that it would misread. It is the wrong
contract if a JavaScript value can wrap or overrun on its way into wasm memory,
if wasm memory leaks across calls, or if the binding holds any search logic.

## Ownership and boundaries

- **The C API owns the algorithm and its refusals**, compiled by Emscripten
  from the same `src/undead_c.cpp` into `undead_wasm.mjs` and `undead_wasm.wasm`.
  It is wasm32, so `size_t` is 32 bits.
- **`bindings/js/undead.mjs` is the binding**: an ES module that converts
  arguments, copies them into wasm memory, calls the C function, copies the
  distances out and frees what it allocated, on every path.
- **The caller names the generated module.** `UndeadLibrary.load(moduleUrl)`
  imports and instantiates it; importing `undead.mjs` loads nothing.
- **The binding checks what wasm cannot see**, before calling:
  - `width`, `height` and every source are integers in `[0, 2^32 - 1]`, since a
    JavaScript number outside that range wraps on its way to a 32-bit `size_t`;
  - `connectivity` is an integer in the 32-bit `int` range, since one outside it
    would arrive as some other `int`, possibly a valid one;
  - `stepCosts` is a `Uint8Array` of exactly `width * height` entries.
- **Distances come back as an `Array` of numbers, `null` where no source
  reaches**, indexed `row * width + column`.

## Errors

- Refused before wasm: `TypeError` for a wrong type, `RangeError` for a value
  out of range or a length mismatch.
- A C status other than `UNDEAD_OK` throws `UndeadError`, whose `status` is the
  status name (`"UNDEAD_ERROR_SOURCE_OUT_OF_RANGE"`, ...).

## Claims and checks

| Claim | Check |
|---|---|
| Distances are shortest paths | Random grids, fixed seeds, against a Bellman-Ford oracle in the tests |
| The game's corridor floods as in C | Hand-worked door corridor |
| Wrong types, ranges and lengths are refused before wasm | One test each, reading the error class |
| Every reachable status maps to `UndeadError` with its name | One test per status; overflow is the 16843010-cell corridor |
| No wasm memory leaks | A test calls it many times on its own module instance, refusals included, and checks the heap does not grow; a heap another test grew would absorb a leak |
| `load` instantiates the module it is named | A test loads the built module and floods a corridor through it |
| The core builds and passes on wasm32 | CTest in the Emscripten build runs the JavaScript suite against the module that build produced |
