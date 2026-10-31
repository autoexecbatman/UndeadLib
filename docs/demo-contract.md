# Dungeon demo - contract

**Spec of the spec.** This contract answers whether a game-shaped caller can use
UndeadLib for the job roguelikes use a Dijkstra map for - monsters walking
toward the player over terrain of different costs - without writing any search
or neighbour code of its own. It is the wrong contract if the demo reimplements
the flood or the neighbour rule, or reaches into the library's internals.

## What it is

- **`demo/DungeonDemo.h`** is the game side: an ASCII map parsed into step
  costs, a player and monsters, and one turn of monster movement. It calls
  `undead::GridGraph` for the grid and its neighbours and
  `undead::DialSearch::dijkstra_map` for the flood; it holds no search.
- **`demo/dungeon_demo.cpp`** runs it: prints each turn's map until every monster
  stands next to the player or a turn limit passes.

## The game rules it shows

- `#` is a wall (cost 0), `.` floor (cost 1), `+` a shut door (cost 2), `@` the
  player, `M` a monster; the player and monsters stand on floor. A cost steers
  which way a monster goes; every monster still moves one cell per turn.
- Eight-way movement; the map is flooded from the player each turn.
- A monster steps to the neighbour with the lowest distance, if that is lower
  than its own; ties go to the first neighbour `GridGraph` offers. A monster
  never enters the player's cell or another monster's, so one already next to
  the player stays.
- Monsters move in reading order, each seeing the cells the earlier ones left.

## Claims and checks

| Claim | Check |
|---|---|
| Parsing gives the costs, player and monsters the map shows | Unit tests, and rendering a parsed map gives the same text back |
| Malformed maps are refused | One test each: ragged rows, an unknown character, no player, two players |
| A monster walks downhill | Corridor case, worked out by hand |
| A door's cost changes the route | A map where the long way round is cheaper than the door |
| Monsters do not stack, and one beside the player stays | Hand cases |
| The demo ends with every monster beside the player | The run's turn count, worked out by hand, and CTest running the executable |
