# C# binding - contract

**Spec of the spec.** This contract answers what a C# caller hands
`undead_dijkstra_map` and gets back, such that no value reaches C that C would
misread. It is the wrong contract if a C# value can wrap or overrun on its way
into C, if the native library can be called after it is unloaded, or if the
binding holds any search logic.

## Ownership and boundaries

- **The C API owns the algorithm and its refusals.** The binding converts
  arguments, calls `undead_c`, and turns each status into an exception.
- **`bindings/csharp/Undead/` is the binding**: one assembly, namespace `Undead`,
  targeting `net10.0`.
- **The caller names the DLL.** `new UndeadLibrary(dllPath)` loads it with
  `NativeLibrary.Load` and calls the export through an unmanaged function
  pointer. No `DllImport` resolver is registered, since a resolver is
  process-wide state; two instances may load two different builds.
  `Dispose` unloads it, and a call after that throws `ObjectDisposedException`.
- **Arguments are idiomatic C#**: `int` sizes and sources, the costs as a
  `ReadOnlySpan<byte>`, the neighbourhood as the `Connectivity` enum.
- **The binding checks what C cannot see**, before calling:
  - `width`, `height` and every source are non-negative, since a negative
    `int` widened to `size_t` becomes a huge index;
  - `stepCosts` has exactly `width * height` entries, computed in `long`.
  An undefined `Connectivity` value is passed through, and C refuses it.
- **Distances come back as `uint?[]`**, `null` where no source reaches,
  indexed `row * width + column`.

## Status to exception

| C status | C# |
|---|---|
| `UNDEAD_ERROR_GRID_SIZE` | `ArgumentException` |
| `UNDEAD_ERROR_SOURCE_OUT_OF_RANGE` | `ArgumentOutOfRangeException` |
| `UNDEAD_ERROR_CONNECTIVITY` | `ArgumentException` |
| `UNDEAD_ERROR_DISTANCE_OVERFLOW` | `OverflowException` |
| `UNDEAD_ERROR_OUT_OF_MEMORY` | `InsufficientMemoryException`, an `OutOfMemoryException`; the base type is reserved for the runtime (CA2201) |
| `UNDEAD_ERROR_NULL_ARGUMENT`, `UNDEAD_ERROR_INTERNAL`, unknown | `InvalidOperationException` - a binding or library defect |

Every exception's message names the C status. An exception from a status carries
no parameter name, since a status does not say which argument C refused.

## Gates

`TreatWarningsAsErrors`, nullable reference types, the recommended .NET
analyzers, and `GenerateDocumentationFile`, which makes a public member with no
XML comment a build error (CS1591). `dotnet format --verify-no-changes` against
`bindings/csharp/.editorconfig`.

## Claims and checks

| Claim | Check |
|---|---|
| Distances are shortest paths | Random grids, fixed seeds, against a Bellman-Ford oracle in the tests |
| The game's corridor floods as in C | Hand-worked door corridor |
| Negative sizes and sources, and wrong-length costs, are refused before C | One test each, reading the exception type and parameter name |
| Every reachable status maps to its exception | One test per status; overflow is the 16843010-cell corridor |
| No call reaches an unloaded library | A test disposes and calls |
| Two instances are independent | A test disposes one and calls the other |
| The gates can fail | Each watched failing once on a deliberate violation |
| The binding works against the DLL the build produced | CTest `csharp_binding` runs `dotnet test` with `UNDEAD_C_DLL` set to `$<TARGET_FILE:undead_c>` |
