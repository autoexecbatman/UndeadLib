// The test oracle for every Dijkstra map: Bellman-Ford relaxation over an
// explicit edge list, plus grid_edges, which lists a grid's edges by its own
// loop over offsets so the oracle never asks GridGraph what its neighbours are.
//
// Usage:
//   const std::vector<uint8_t> costs{ 1, 0, 2 };
//   const std::vector<OracleEdge> edges = grid_edges(3, 1, costs, false);
//   const std::vector<size_t> sources{ 0 };
//   bellman_ford(3, edges, sources);  // -> { 0, nullopt, nullopt }
#pragma once

#include <cstdint>
#include <optional>
#include <span>
#include <vector>

namespace undead_test
{
	// One directed edge: stepping from `from` onto `to` costs stepCost.
	struct OracleEdge
	{
		size_t from{ 0 };
		size_t to{ 0 };
		uint32_t stepCost{ 0 };
	};

	// Every edge of a row-major grid where entering a cell costs its value and
	// a 0 cell cannot be entered. Diagonals are included when eightWay is true.
	//
	// Example:
	//   grid_edges(2, 1, std::vector<uint8_t>{ 1, 3 }, false);
	//   // -> { {0, 1, 3}, {1, 0, 1} }
	inline std::vector<OracleEdge> grid_edges(
		size_t width,
		size_t height,
		std::span<const uint8_t> costs,
		bool eightWay)
	{
		std::vector<OracleEdge> edges;
		for (size_t row = 0; row < height; ++row)
		{
			for (size_t column = 0; column < width; ++column)
			{
				for (int rowOffset = -1; rowOffset <= 1; ++rowOffset)
				{
					for (
						int columnOffset = -1; columnOffset <= 1;
						++columnOffset)
					{
						const bool isSelf = rowOffset == 0 && columnOffset == 0;
						const bool isDiagonal =
							rowOffset != 0 && columnOffset != 0;
						if (isSelf || (isDiagonal && !eightWay))
						{
							continue;
						}
						// Signed arithmetic, so a step off the west or north edge
						// is a negative coordinate rather than a wrapped one.
						const long long nextRow =
							static_cast<long long>(row) + rowOffset;
						const long long nextColumn =
							static_cast<long long>(column) + columnOffset;
						if (nextRow < 0 || nextColumn < 0 ||
							nextRow >= static_cast<long long>(height) ||
							nextColumn >= static_cast<long long>(width))
						{
							continue;
						}
						const size_t to = static_cast<size_t>(nextRow) * width +
							static_cast<size_t>(nextColumn);
						if (costs[to] == 0)
						{
							continue;
						}
						edges.push_back(
							OracleEdge{ row * width + column, to, costs[to] });
					}
				}
			}
		}
		return edges;
	}

	// Shortest distances from the nearest source by repeated relaxation of
	// every edge until nothing changes; nullopt where no source reaches.
	// Distances are 64-bit so the oracle itself cannot overflow.
	//
	// Example:
	//   bellman_ford(3, { {0, 1, 4}, {1, 2, 1}, {0, 2, 9} }, { 0 });
	//   // -> { 0, 4, 5 }
	inline std::vector<std::optional<uint64_t>> bellman_ford(
		size_t nodeCount,
		std::span<const OracleEdge> edges,
		std::span<const size_t> sources)
	{
		std::vector<std::optional<uint64_t>> distances(nodeCount, std::nullopt);
		for (const size_t source : sources)
		{
			distances[source] = 0;
		}
		bool isChanged = true;
		while (isChanged)
		{
			isChanged = false;
			for (const OracleEdge& edge : edges)
			{
				if (!distances[edge.from])
				{
					continue;
				}
				const uint64_t candidate =
					*distances[edge.from] + edge.stepCost;
				if (!distances[edge.to] || candidate < *distances[edge.to])
				{
					distances[edge.to] = candidate;
					isChanged = true;
				}
			}
		}
		return distances;
	}
} // namespace undead_test
