// The C API in undead.h, as a thin layer over the C++ core: it converts the
// arguments, calls DialSearch, copies the distances out, and turns every
// exception into a status code so none crosses into C.
#include <cstdint>
#include <new>
#include <optional>
#include <span>
#include <stdexcept>

#include "undead/DialSearch.h"
#include "undead/DistanceMap.h"
#include "undead/GridGraph.h"
#include "undead/undead.h"

int undead_dijkstra_map(
	const undead_grid* grid,
	int connectivity,
	const size_t* sources,
	size_t source_count,
	uint32_t* distances)
{
	// Pointer and enum checks the C++ core has no counterpart for.
	if (grid == nullptr || (sources == nullptr && source_count != 0))
	{
		return UNDEAD_ERROR_NULL_ARGUMENT;
	}
	const std::optional<size_t> cellCount =
		undead::GridGraph::cell_count(grid->width, grid->height);
	if (!cellCount)
	{
		return UNDEAD_ERROR_GRID_SIZE;
	}
	if (*cellCount != 0 &&
		(grid->step_costs == nullptr || distances == nullptr))
	{
		return UNDEAD_ERROR_NULL_ARGUMENT;
	}
	if (connectivity != UNDEAD_FOUR_WAY && connectivity != UNDEAD_EIGHT_WAY)
	{
		return UNDEAD_ERROR_CONNECTIVITY;
	}

	try
	{
		const undead::GridGraph graph{
			grid->width,
			grid->height,
			std::span<const uint8_t>{ grid->step_costs, *cellCount },
			connectivity == UNDEAD_EIGHT_WAY ? undead::Connectivity::EIGHT :
											   undead::Connectivity::FOUR,
		};
		const undead::DistanceMap map = undead::DialSearch::dijkstra_map(
			graph,
			std::span<const size_t>{ sources, source_count },
			undead::GridGraph::max_step_cost());

		// Written only now, after the search succeeded.
		for (size_t cell = 0; cell < *cellCount; ++cell)
		{
			distances[cell] = map.distance(cell).value_or(UNDEAD_UNREACHED);
		}
		return UNDEAD_OK;
	}
	catch (const std::out_of_range&)
	{
		return UNDEAD_ERROR_SOURCE_OUT_OF_RANGE;
	}
	catch (const std::overflow_error&)
	{
		return UNDEAD_ERROR_DISTANCE_OVERFLOW;
	}
	catch (const std::bad_alloc&)
	{
		return UNDEAD_ERROR_OUT_OF_MEMORY;
	}
	catch (...)
	{
		return UNDEAD_ERROR_INTERNAL;
	}
}
