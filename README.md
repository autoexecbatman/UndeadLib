# UndeadLib

The grid algorithms a roguelike ends up writing in every project, written once: a C++20
header-only core, a C API over it, and bindings for Python, JavaScript and C#.

What it does today: **Dijkstra maps** over a grid of step costs, computed with Dial's
algorithm (a bucket queue, which suits small integer costs). A* routes and field of view
are planned and not yet written.

A grid is one byte per cell, row after row: `0` is a wall, and `1` to `255` is the cost of
stepping onto the cell. Cell `(column, row)` is index `row * width + column` everywhere.
Movement is four-way or eight-way. A Dijkstra map gives each cell its distance to the nearest
source. A monster that steps downhill on it chases the player, and one that steps uphill flees.

## Using it

Every example below floods the same corridor: seven cells, with a door at column 4 that costs
2 to enter.

**C** (`include/undead/undead.h`, linked against `undead_c`):

```c
const uint8_t costs[7] = { 1, 1, 1, 1, 2, 1, 1 };
const size_t sources[1] = { 0 };
uint32_t distances[7];
int status = undead_dijkstra_map(7, 1, costs, UNDEAD_EIGHT_WAY, sources, 1, distances);
// status == UNDEAD_OK, distances == { 0, 1, 2, 3, 5, 6, 7 }
```

Every function returns a status, and on an error the output array is left unwritten. A cell
no source reaches holds `UNDEAD_UNREACHED`.

**C++** (header-only, `include/undead/`):

```cpp
const std::vector<uint8_t> costs{ 1, 1, 1, 1, 2, 1, 1 };
const undead::GridGraph corridor{ 7, 1, costs, undead::Connectivity::EIGHT };
const std::vector<size_t> sources{ 0 };
const undead::DistanceMap map =
    undead::DialSearch::dijkstra_map(corridor, sources, corridor.max_step_cost());
map.distance(4);  // -> 5, std::optional<uint32_t>; empty where unreached
```

`DialSearch` works on any graph that satisfies its `SearchGraph` concept, not just
`GridGraph`.

**Python** (`bindings/python`, ctypes over `undead_c`):

```python
from pathlib import Path

import undead

library = undead.UndeadLibrary(Path("build/bin/Release/undead_c.dll"))
library.dijkstra_map(7, 1, bytes([1, 1, 1, 1, 2, 1, 1]),
                     undead.Connectivity.EIGHT_WAY, [0])
# -> [0, 1, 2, 3, 5, 6, 7]; None where unreached
```

**JavaScript** (`bindings/js/undead.mjs`, over a WebAssembly build; Node or a browser):

```js
import { Connectivity, UndeadLibrary } from "./undead.mjs";

const library = await UndeadLibrary.load(new URL("./undead_wasm.mjs", import.meta.url));
library.dijkstraMap(7, 1, Uint8Array.from([1, 1, 1, 1, 2, 1, 1]), Connectivity.EIGHT_WAY, [0]);
// -> [0, 1, 2, 3, 5, 6, 7]; null where unreached
```

**C#** (`bindings/csharp/Undead`, net10.0, over `undead_c`):

```csharp
using var library = new UndeadLibrary("build/bin/Release/undead_c.dll");
byte[] costs = [1, 1, 1, 1, 2, 1, 1];
library.DijkstraMap(7, 1, costs, Connectivity.EightWay, [0]);
// -> { 0, 1, 2, 3, 5, 6, 7 }; null where unreached
```

Each binding checks what C cannot see before calling it, such as a negative size or a
cost array of the wrong length. It turns the C status into that language's own error.
Each binding's contract is in `docs/`: `python-binding-contract.md`, `js-binding-contract.md`
and `csharp-binding-contract.md`.

## The demo

`demo/` is the library used the way a game uses it, with no search code of its own. Monsters
(`M`) chase the player (`@`) down a Dijkstra map, and the door (`+`) costs 2 to cross:

```
Turn 0
##############
#M...#.......#
#....+...@...#
#....#.......#
#.####...M...#
#............#
#M...........#
##############
...
Caught after 7 turns.
```

## Building

The core is C++20 and builds with CMake. GoogleTest comes through vcpkg (`vcpkg.json`).

```
cmake -S . -B build -DCMAKE_TOOLCHAIN_FILE=<vcpkg>/scripts/buildsystems/vcpkg.cmake
cmake --build build --config Release
ctest --test-dir build -C Release --output-on-failure
```

That runs everything except the JavaScript suite: the C++ tests, the dungeon demo, and the
Python and C# suites against the `undead_c` the build produced. It also runs the
documentation checks. The Python suite needs `pytest`, the C# one the .NET 10 SDK, and the
documentation pip's `libclang`.

The JavaScript binding needs its own build, done with Emscripten:

```
emcmake cmake -S . -B build-wasm -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build-wasm
ctest --test-dir build-wasm --output-on-failure
```

That runs the JavaScript suite under Node, and runs the demo compiled to wasm32.

## Documentation

```
cmake --build build --config Release --target docs
```

This writes `build/docs/api.html`, one self-contained page covering the C API, the C++ core
and all three bindings. The page is generated from the comments in the source. The
`docs_coverage` test fails when a public declaration has no comment.

## How it is tested

- **Every distance is checked against an independent oracle.** The C++ tests use a
  Bellman-Ford solver in `tests/BellmanFordOracle.h`. Each binding's suite uses its own
  Bellman-Ford over random grids with fixed seeds.
- **Every refusal and every C status has a test.** This includes the boundary where a
  distance would reach `UINT32_MAX`.
- **The test suites are themselves tested by mutation.** The `mutations*.json` files in
  `tests/`, `demo/`, `docs/` and each binding list deliberate breakages of the code. Each one
  must make a test fail.

## Layout

| Path | What it holds |
|---|---|
| `include/undead/` | The C++20 core (`DialSearch.h`, `GridGraph.h`, `DistanceMap.h`) and the C API (`undead.h`) |
| `src/undead_c.cpp` | The C API over the core; no algorithm of its own |
| `tests/` | GoogleTest suite and the Bellman-Ford oracle |
| `bindings/` | `python/`, `js/`, `csharp/` |
| `demo/` | The dungeon chase |
| `docs/` | Contracts, and the API page generator |
| `cmake/` | The Emscripten half of the build |
| `seed/` | Reference copies of the game code the library was extracted from; not built |
