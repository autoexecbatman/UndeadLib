/**
 * @file undead.h
 * @brief The C API of UndeadLib: grid algorithms that take arrays and fill
 * arrays, for C callers and for language bindings. Valid C11 and C++.
 *
 * Every function returns an int status: UNDEAD_OK (0), or one of the
 * UNDEAD_ERROR_ codes below. On any error the output array is not written.
 * Arrays are row-major: cell (column, row) is index row * width + column.
 *
 * Usage, the game's corridor with a shut door at column 4:
 * @code
 *   const uint8_t costs[7] = { 1, 1, 1, 1, 2, 1, 1 };  // 0 would be a wall
 *   const undead_grid grid = { 7, 1, costs };            // width, height, costs
 *   const size_t sources[1] = { 0 };                     // flood from cell 0
 *   uint32_t distances[7];                               // one per cell
 *   int status = undead_dijkstra_map(
 *       &grid, UNDEAD_EIGHT_WAY, sources, 1, distances);
 *   // status == UNDEAD_OK, distances == { 0, 1, 2, 3, 5, 6, 7 }
 *   const size_t far[1] = { 7 };
 *   status = undead_dijkstra_map(&grid, UNDEAD_EIGHT_WAY, far, 1, distances);
 *   // status == UNDEAD_ERROR_SOURCE_OUT_OF_RANGE, distances unchanged
 * @endcode
 */
#pragma once

#include <stddef.h>
#include <stdint.h>

#if defined(_WIN32)
#if defined(UNDEAD_BUILDING_DLL)
#define UNDEAD_API __declspec(dllexport)
#else
#define UNDEAD_API __declspec(dllimport)
#endif
#else
#define UNDEAD_API __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
extern "C"
{
#endif

	/** A distance no source reaches. */
#define UNDEAD_UNREACHED UINT32_MAX

	/** Status codes every function returns. */
	enum
	{
		UNDEAD_OK = 0,
		/** A required pointer was NULL. */
		UNDEAD_ERROR_NULL_ARGUMENT = 1,
		/** width * height overflows, or does not match the array. */
		UNDEAD_ERROR_GRID_SIZE = 2,
		/** A source index is not a cell of the grid. */
		UNDEAD_ERROR_SOURCE_OUT_OF_RANGE = 3,
		/** connectivity is neither UNDEAD_FOUR_WAY nor UNDEAD_EIGHT_WAY. */
		UNDEAD_ERROR_CONNECTIVITY = 4,
		/** A distance would reach UNDEAD_UNREACHED. */
		UNDEAD_ERROR_DISTANCE_OVERFLOW = 5,
		/** The search could not allocate its working memory. */
		UNDEAD_ERROR_OUT_OF_MEMORY = 6,
		/** A failure the library did not anticipate; a library defect. */
		UNDEAD_ERROR_INTERNAL = 7
	};

	/** Neighbourhoods: the four sharing an edge, or those and the diagonals. */
	enum
	{
		UNDEAD_FOUR_WAY = 4,
		UNDEAD_EIGHT_WAY = 8
	};

	/**
	 * A grid of step costs. step_costs holds width * height entries; 0 is a
	 * wall, 1 to 255 is the cost of stepping onto the cell. Not copied.
	 */
	typedef struct undead_grid
	{
		size_t width;
		size_t height;
		const uint8_t* step_costs;
	} undead_grid;

	/**
	 * Fills distances with the cheapest cost from the nearest source to every
	 * cell, or UNDEAD_UNREACHED where none reaches. A source is at distance 0
	 * whatever its own cost.
	 *
	 * grid: required. step_costs may be NULL only when width * height is 0.
	 * connectivity: UNDEAD_FOUR_WAY or UNDEAD_EIGHT_WAY.
	 * sources: source_count cell indices; NULL only when source_count is 0.
	 * distances: width * height entries, written only on UNDEAD_OK; NULL only
	 * when width * height is 0.
	 */
	UNDEAD_API int undead_dijkstra_map(
		const undead_grid* grid,
		int connectivity,
		const size_t* sources,
		size_t source_count,
		uint32_t* distances);

#ifdef __cplusplus
}
#endif
