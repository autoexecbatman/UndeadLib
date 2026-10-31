/*
 * A C caller of undead.h. Compiled as C, so a C++-only construct in the
 * header fails the build; CApiTest calls these functions to check the
 * results a C program actually gets.
 *
 * Usage, from C++:
 *   extern "C" int c_caller_door_corridor(uint32_t* distances);
 *   uint32_t distances[7];
 *   c_caller_door_corridor(distances);  // -> UNDEAD_OK, { 0, 1, 2, 3, 5, 6, 7 }
 */
#include "undead/undead.h"

/* Floods C++RogueLike's corridor, with a shut door at column 4, from cell 0. */
int c_caller_door_corridor(uint32_t* distances)
{
	const uint8_t costs[7] = { 1, 1, 1, 1, 2, 1, 1 };
	const undead_grid grid = { 7, 1, costs };
	const size_t sources[1] = { 0 };
	return undead_dijkstra_map(&grid, UNDEAD_EIGHT_WAY, sources, 1, distances);
}
