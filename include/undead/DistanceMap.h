/**
 * @file DistanceMap.h
 * @brief The result of a Dijkstra flood: the cheapest distance from the
 * nearest source to every node, or nothing for a node no source reaches.
 *
 * A DistanceMap is produced by DialSearch::dijkstra_map and only read by the
 * caller. Nodes are indices in [0, node_count()), the same indices the graph
 * that was searched uses; for a GridGraph a cell is row * width + column.
 *
 * Usage, a corridor of seven floor cells flooded from its west end:
 * @code
 *   const std::vector<uint8_t> costs(7, 1);       // every cell costs 1 to enter
 *   const undead::GridGraph corridor{ 7, 1, costs, undead::Connectivity::FOUR };
 *   const std::vector<size_t> sources{ 0 };        // cell (0, 0)
 *   const undead::DistanceMap map =
 *       undead::DialSearch::dijkstra_map(corridor, sources, corridor.max_step_cost());
 *   map.node_count();  // -> 7
 *   map.distance(6);   // -> 6, six steps east
 *   map.distance(7);   // throws std::out_of_range: there is no node 7
 * @endcode
 */
#pragma once

#include <cstdint>
#include <optional>
#include <stdexcept>
#include <vector>

namespace undead
{
	class DialSearch;

	/**
	 * @brief Cheapest distance to each node from the nearest source.
	 *
	 * Example, a 3x1 row of costs { 1, 0, 1 } flooded from cell 0:
	 * @code
	 *   map.distance(0);  // -> 0, the source
	 *   map.distance(2);  // -> nullopt, the wall at cell 1 cuts it off
	 * @endcode
	 */
	class DistanceMap
	{
	private:
		// The value a node holds until a source reaches it.
		static constexpr uint32_t UNREACHED = UINT32_MAX;

		std::vector<uint32_t> distances{};

		explicit DistanceMap(size_t nodeCount) :
			distances(nodeCount, UNREACHED)
		{
		}

		friend class DialSearch;

	public:
		/**
		 * @brief How many nodes the searched graph has.
		 */
		[[nodiscard]] size_t node_count() const noexcept
		{
			return distances.size();
		}

		/**
		 * @brief The cheapest distance from any source to the node.
		 * @param[in] node An index in [0, node_count()).
		 * @returns The distance, or nullopt when no source reaches the node.
		 * @throws std::out_of_range when the node is not in the graph.
		 */
		[[nodiscard]] std::optional<uint32_t> distance(size_t node) const
		{
			if (node >= distances.size())
			{
				throw std::out_of_range(
					"DistanceMap::distance: node is not in the graph");
			}
			if (distances[node] == UNREACHED)
			{
				return std::nullopt;
			}
			return distances[node];
		}
	};
} // namespace undead
