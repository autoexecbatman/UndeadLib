// DialSearch::dijkstra_map: hand-derived floods over small grids and graphs,
// agreement with the Bellman-Ford oracle on random ones, and every refusal.
#include <cstdint>
#include <optional>
#include <random>
#include <span>
#include <stdexcept>
#include <vector>

#include <gtest/gtest.h>

#include "BellmanFordOracle.h"
#include "undead/DialSearch.h"
#include "undead/DistanceMap.h"
#include "undead/GridGraph.h"

namespace
{
	using undead_test::OracleEdge;

	// A graph given as an explicit edge list, for portals and zero-cost edges.
	struct ListGraph
	{
		size_t nodeCount{ 0 };
		std::vector<OracleEdge> edges{};

		size_t node_count() const noexcept { return nodeCount; }

		template <typename Visitor>
		void for_each_neighbour(size_t node, Visitor&& visit) const
		{
			for (const OracleEdge& edge : edges)
			{
				if (edge.from == node)
				{
					visit(edge.to, edge.stepCost);
				}
			}
		}
	};

	// Node k steps to node k + 1 at a fixed cost, so node k is at k * stepCost.
	struct ChainGraph
	{
		size_t nodeCount{ 0 };
		uint32_t stepCost{ 0 };

		size_t node_count() const noexcept { return nodeCount; }

		template <typename Visitor>
		void for_each_neighbour(size_t node, Visitor&& visit) const
		{
			if (node + 1 < nodeCount)
			{
				visit(node + 1, stepCost);
			}
		}
	};

	std::vector<std::optional<uint32_t>> all_distances(
		const undead::DistanceMap& map)
	{
		std::vector<std::optional<uint32_t>> distances;
		for (size_t node = 0; node < map.node_count(); ++node)
		{
			distances.push_back(map.distance(node));
		}
		return distances;
	}

	std::vector<std::optional<uint32_t>> flood_grid(
		size_t width,
		size_t height,
		const std::vector<uint8_t>& costs,
		undead::Connectivity connectivity,
		const std::vector<size_t>& sources)
	{
		const undead::GridGraph grid{ width, height, costs, connectivity };
		return all_distances(
			undead::DialSearch::dijkstra_map(
				grid,
				sources,
				grid.max_step_cost()));
	}

	// The oracle's answer narrowed to the library's type; every distance in
	// these tests is far below UINT32_MAX.
	std::vector<std::optional<uint32_t>> narrowed(
		const std::vector<std::optional<uint64_t>>& wide)
	{
		std::vector<std::optional<uint32_t>> narrow;
		for (const std::optional<uint64_t>& distance : wide)
		{
			narrow.push_back(
				distance ? std::optional<uint32_t>{ static_cast<uint32_t>(
							   *distance) } :
						   std::nullopt);
		}
		return narrow;
	}

	constexpr std::nullopt_t UNREACHED = std::nullopt;
} // namespace

TEST(DialSearch, CorridorDistanceCountsSteps)
{
	const std::vector<uint8_t> costs(7, 1);
	const std::vector<std::optional<uint32_t>> expected{ 0, 1, 2, 3, 4, 5, 6 };
	EXPECT_EQ(
		flood_grid(7, 1, costs, undead::Connectivity::FOUR, { 0 }),
		expected);
}

TEST(DialSearch, ShutDoorCostsTwoToEnter)
{
	// C++RogueLike's corridor: floor costs 1, the shut door at column 4 costs 2.
	const std::vector<uint8_t> costs{ 1, 1, 1, 1, 2, 1, 1 };
	const std::vector<std::optional<uint32_t>> expected{ 0, 1, 2, 3, 5, 6, 7 };
	EXPECT_EQ(
		flood_grid(7, 1, costs, undead::Connectivity::EIGHT, { 0 }),
		expected);
}

TEST(DialSearch, WallLeavesTheFarSideUnreached)
{
	const std::vector<uint8_t> costs{ 1, 0, 1 };
	const std::vector<std::optional<uint32_t>> expected{ 0,
		UNREACHED,
		UNREACHED };
	EXPECT_EQ(
		flood_grid(3, 1, costs, undead::Connectivity::FOUR, { 0 }),
		expected);
}

TEST(DialSearch, SourceOnAWallIsAtZeroAndFloodsOut)
{
	const std::vector<uint8_t> costs{ 0, 1, 1 };
	const std::vector<std::optional<uint32_t>> expected{ 0, 1, 2 };
	EXPECT_EQ(
		flood_grid(3, 1, costs, undead::Connectivity::FOUR, { 0 }),
		expected);
}

TEST(DialSearch, TwoSourcesMeetInTheMiddle)
{
	const std::vector<uint8_t> costs(5, 1);
	const std::vector<std::optional<uint32_t>> expected{ 0, 1, 2, 1, 0 };
	EXPECT_EQ(
		flood_grid(5, 1, costs, undead::Connectivity::FOUR, { 0, 4 }),
		expected);
}

TEST(DialSearch, DuplicateSourceIsOneSource)
{
	const std::vector<uint8_t> costs(4, 1);
	const std::vector<std::optional<uint32_t>> expected{ 0, 1, 2, 3 };
	EXPECT_EQ(
		flood_grid(4, 1, costs, undead::Connectivity::FOUR, { 0, 0 }),
		expected);
}

TEST(DialSearch, NoSourcesLeavesEveryNodeUnreached)
{
	const std::vector<uint8_t> costs(3, 1);
	const std::vector<std::optional<uint32_t>> expected{ UNREACHED,
		UNREACHED,
		UNREACHED };
	EXPECT_EQ(
		flood_grid(3, 1, costs, undead::Connectivity::FOUR, {}),
		expected);
}

TEST(DialSearch, EightWayCutsTheCornerFourWayWalksIt)
{
	// From the top-left of a 3x3 open room to the bottom-right: four steps
	// along the edges, or two diagonals.
	const std::vector<uint8_t> costs(9, 1);
	EXPECT_EQ(
		flood_grid(3, 3, costs, undead::Connectivity::FOUR, { 0 })[8],
		4u);
	EXPECT_EQ(
		flood_grid(3, 3, costs, undead::Connectivity::EIGHT, { 0 })[8],
		2u);
}

TEST(DialSearch, ZeroCostPortalIsTaken)
{
	// 0 -1-> 1 -1-> 2 -1-> 3, a free portal 0 -> 3, and 3 -5-> 2.
	const ListGraph graph{
		4,
		{ { 0, 1, 1 }, { 1, 2, 1 }, { 2, 3, 1 }, { 0, 3, 0 }, { 3, 2, 5 } },
	};
	const std::vector<size_t> sources{ 0 };
	const std::vector<std::optional<uint32_t>> expected{ 0, 1, 2, 0 };
	EXPECT_EQ(
		all_distances(undead::DialSearch::dijkstra_map(graph, sources, 5)),
		expected);
}

TEST(DialSearch, StepCostEqualToTheBoundIsAccepted)
{
	// A cost equal to maxStepCost lands in the bucket just behind the current
	// one, which is the wrap-around case of the circular queue.
	const ChainGraph chain{ 4, 3 };
	const std::vector<size_t> sources{ 0 };
	const std::vector<std::optional<uint32_t>> expected{ 0, 3, 6, 9 };
	EXPECT_EQ(
		all_distances(undead::DialSearch::dijkstra_map(chain, sources, 3)),
		expected);
}

TEST(DialSearch, MatchesBellmanFordOnRandomGrids)
{
	for (uint32_t seed = 1; seed <= 200; ++seed)
	{
		std::mt19937 random{ seed };
		std::uniform_int_distribution<size_t> sideLength{ 1, 16 };
		const size_t width = sideLength(random);
		const size_t height = sideLength(random);

		// Odd seeds draw costs 1..4, even seeds the full byte range, so both
		// short and long bucket rings are exercised; a fifth of cells are walls.
		const int highestCost = seed % 2 == 1 ? 4 : 255;
		std::uniform_int_distribution<int> cost{ 1, highestCost };
		std::bernoulli_distribution isWall{ 0.2 };
		std::vector<uint8_t> costs(width * height);
		for (uint8_t& cell : costs)
		{
			cell = isWall(random) ? uint8_t{ 0 } :
									static_cast<uint8_t>(cost(random));
		}

		std::uniform_int_distribution<size_t> cell{ 0, width * height - 1 };
		std::uniform_int_distribution<int> sourceCount{ 1, 3 };
		std::vector<size_t> sources;
		for (int count = sourceCount(random); count > 0; --count)
		{
			sources.push_back(cell(random));
		}

		for (const bool eightWay : { false, true })
		{
			const undead::Connectivity connectivity = eightWay ?
				undead::Connectivity::EIGHT :
				undead::Connectivity::FOUR;
			const std::vector<OracleEdge> edges =
				undead_test::grid_edges(width, height, costs, eightWay);
			EXPECT_EQ(
				flood_grid(width, height, costs, connectivity, sources),
				narrowed(
					undead_test::bellman_ford(width * height, edges, sources)))
				<< "seed " << seed << ", eightWay " << eightWay;
		}
	}
}

TEST(DialSearch, MatchesBellmanFordOnRandomGraphsWithZeroCostEdges)
{
	for (uint32_t seed = 1; seed <= 200; ++seed)
	{
		std::mt19937 random{ seed };
		std::uniform_int_distribution<size_t> nodeCount{ 1, 40 };
		ListGraph graph{ nodeCount(random), {} };

		std::uniform_int_distribution<size_t> node{ 0, graph.nodeCount - 1 };
		std::uniform_int_distribution<uint32_t> stepCost{ 0, 7 };
		std::uniform_int_distribution<size_t> edgeCount{ 0, 120 };
		for (size_t count = edgeCount(random); count > 0; --count)
		{
			const size_t from = node(random);
			const size_t to = node(random);
			graph.edges.push_back(OracleEdge{ from, to, stepCost(random) });
		}
		const std::vector<size_t> sources{ node(random) };

		EXPECT_EQ(
			all_distances(undead::DialSearch::dijkstra_map(graph, sources, 7)),
			narrowed(
				undead_test::bellman_ford(
					graph.nodeCount,
					graph.edges,
					sources)))
			<< "seed " << seed;
	}
}

TEST(DialSearch, RefusesASourceOutsideTheGraph)
{
	const ChainGraph chain{ 3, 1 };
	const std::vector<size_t> sources{ 3 };
	EXPECT_THROW(
		(void)undead::DialSearch::dijkstra_map(chain, sources, 1),
		std::out_of_range);
}

TEST(DialSearch, RefusesANeighbourOutsideTheGraph)
{
	// Node 3 is one past the last node of a three-node graph.
	const ListGraph graph{ 3, { { 0, 3, 1 } } };
	const std::vector<size_t> sources{ 0 };
	EXPECT_THROW(
		(void)undead::DialSearch::dijkstra_map(graph, sources, 1),
		std::out_of_range);
}

TEST(DialSearch, RefusesAStepCostAboveTheBound)
{
	const ChainGraph chain{ 3, 6 };
	const std::vector<size_t> sources{ 0 };
	EXPECT_THROW(
		(void)undead::DialSearch::dijkstra_map(chain, sources, 5),
		std::invalid_argument);
}

TEST(DialSearch, LargestDistanceBelowUint32MaxIsKept)
{
	// 65535 * 65536 = 4294901760, the last node of a 65537-node chain.
	const ChainGraph chain{ 65537, 65535 };
	const std::vector<size_t> sources{ 0 };
	const undead::DistanceMap map =
		undead::DialSearch::dijkstra_map(chain, sources, 65535);
	EXPECT_EQ(map.distance(65536), 4294901760u);
}

TEST(DialSearch, RefusesADistanceThatReachesUint32Max)
{
	// 65535 * 65537 = 4294967295 = UINT32_MAX, node 65537 of a 65538-node chain.
	const ChainGraph chain{ 65538, 65535 };
	const std::vector<size_t> sources{ 0 };
	EXPECT_THROW(
		(void)undead::DialSearch::dijkstra_map(chain, sources, 65535),
		std::overflow_error);
}

TEST(DistanceMap, RefusesANodeOutsideTheMap)
{
	const ChainGraph chain{ 3, 1 };
	const std::vector<size_t> sources{ 0 };
	const undead::DistanceMap map =
		undead::DialSearch::dijkstra_map(chain, sources, 1);
	EXPECT_THROW((void)map.distance(3), std::out_of_range);
}
