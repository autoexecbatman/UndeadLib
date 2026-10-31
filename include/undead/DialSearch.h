/**
 * @file DialSearch.h
 * @brief Dijkstra maps by Dial's algorithm: Dijkstra's algorithm with a
 * circular bucket queue, for graphs whose step costs are small integers.
 *
 * A Dijkstra map holds, for every node, the cheapest distance from the
 * nearest of a set of sources. The graph is anything satisfying SearchGraph:
 * it says how many nodes it has and, for a node, calls a visitor once per
 * outgoing edge with the neighbour and the step cost. GridGraph is the
 * ready-made one; a graph with portals or one-way edges is written by the
 * caller in the same shape.
 *
 * Usage, the game's corridor with a shut door at column 4:
 * @code
 *   const std::vector<uint8_t> costs{ 1, 1, 1, 1, 2, 1, 1 };
 *   const undead::GridGraph corridor{ 7, 1, costs, undead::Connectivity::EIGHT };
 *   const std::vector<size_t> sources{ 0 };
 *   const undead::DistanceMap map = undead::DialSearch::dijkstra_map(
 *       corridor,                  // the graph
 *       sources,                   // nodes the flood starts from, at distance 0
 *       corridor.max_step_cost()); // no edge costs more than this
 *   map.distance(4);  // -> 5, the door costs 2 to enter
 *   map.distance(6);  // -> 7
 * @endcode
 */
#pragma once

#include <concepts>
#include <cstdint>
#include <limits>
#include <span>
#include <stdexcept>
#include <vector>

#include "undead/DistanceMap.h"

namespace undead
{
	/**
	 * @brief A graph DialSearch can flood: node_count(), and
	 * for_each_neighbour(node, visit) calling visit(next, stepCost) per edge.
	 */
	template <typename Graph>
	concept SearchGraph = requires(
		const Graph& graph,
		size_t node,
		void (*visit)(size_t, uint32_t)) {
		{ graph.node_count() } -> std::same_as<size_t>;
		graph.for_each_neighbour(node, visit);
	};

	/**
	 * @brief Dijkstra maps over graphs with integer step costs in
	 * [0, maxStepCost].
	 */
	class DialSearch
	{
	public:
		/**
		 * @brief Floods the graph from every source and returns the cheapest
		 * distance to each node. A source is at distance 0 whatever it would
		 * cost to enter.
		 *
		 * @param[in] graph The graph to flood.
		 * @param[in] sources Node indices; duplicates are allowed, and none
		 * leaves every node unreached.
		 * @param[in] maxStepCost The largest step cost the graph reports.
		 * Allocates maxStepCost + 1 buckets, and time grows with the largest
		 * distance reached as well as with the graph, since every distance
		 * value up to it is visited once.
		 * @throws std::out_of_range when a source or a reported neighbour is
		 * not a node of the graph.
		 * @throws std::invalid_argument when the graph reports a step cost
		 * above maxStepCost.
		 * @throws std::overflow_error when a distance would reach UINT32_MAX.
		 * @throws std::length_error when maxStepCost + 1 does not fit in size_t.
		 */
		template <SearchGraph Graph>
		[[nodiscard]] static DistanceMap dijkstra_map(
			const Graph& graph,
			std::span<const size_t> sources,
			uint32_t maxStepCost)
		{
			const size_t nodeCount = graph.node_count();
			DistanceMap result{ nodeCount };
			std::vector<uint32_t>& distances = result.distances;

			// Where size_t is 32 bits, UINT32_MAX + 1 buckets cannot be counted.
			if (uint64_t{ maxStepCost } + 1 >
				std::numeric_limits<size_t>::max())
			{
				throw std::length_error(
					"DialSearch::dijkstra_map: maxStepCost + 1 buckets do not fit in size_t");
			}
			// Bucket d % bucketCount holds nodes tentatively at distance d. Every
			// pending distance lies in [current, current + maxStepCost], so the
			// ring never holds two distances in one bucket.
			const size_t bucketCount = size_t{ maxStepCost } + 1;
			std::vector<std::vector<size_t>> buckets(bucketCount);
			size_t pendingCount = 0;

			for (const size_t source : sources)
			{
				if (source >= nodeCount)
				{
					throw std::out_of_range(
						"DialSearch::dijkstra_map: a source is not a node of the graph");
				}
				distances[source] = 0;
				buckets[0].push_back(source);
				++pendingCount;
			}

			uint64_t current = 0;
			// current % bucketCount, advanced by comparison rather than division.
			size_t currentSlot = 0;
			while (pendingCount > 0)
			{
				std::vector<size_t>& bucket = buckets[currentSlot];

				// Lowers a neighbour's distance through the settled node; a
				// zero-cost edge refills the bucket being drained.
				const auto relax = [&](size_t next, uint32_t stepCost)
				{
					if (next >= nodeCount)
					{
						throw std::out_of_range(
							"DialSearch::dijkstra_map: the graph reported a neighbour that is not a node");
					}
					if (stepCost > maxStepCost)
					{
						throw std::invalid_argument(
							"DialSearch::dijkstra_map: the graph reported a step cost above maxStepCost");
					}
					const uint64_t candidate = current + stepCost;
					if (candidate >= DistanceMap::UNREACHED)
					{
						throw std::overflow_error(
							"DialSearch::dijkstra_map: a distance reached UINT32_MAX");
					}
					if (candidate < distances[next])
					{
						distances[next] = static_cast<uint32_t>(candidate);
						// stepCost < bucketCount, so one subtraction wraps the ring.
						const size_t slot = currentSlot + stepCost;
						buckets[slot >= bucketCount ? slot - bucketCount : slot]
							.push_back(next);
						++pendingCount;
					}
				};

				while (!bucket.empty())
				{
					const size_t node = bucket.back();
					bucket.pop_back();
					--pendingCount;
					// A node queued again at a lower distance left this entry
					// stale; it was settled when that lower bucket drained.
					if (distances[node] != current)
					{
						continue;
					}
					graph.for_each_neighbour(node, relax);
				}
				++current;
				currentSlot =
					currentSlot + 1 == bucketCount ? 0 : currentSlot + 1;
			}
			return result;
		}
	};
} // namespace undead
