// GridGraph: size validation, and which neighbours a cell reports at what
// cost. Expected neighbour sets are worked out by hand from the grid drawn
// in each test.
#include <algorithm>
#include <compare>
#include <cstdint>
#include <limits>
#include <stdexcept>
#include <vector>

#include <gtest/gtest.h>

#include "undead/GridGraph.h"

namespace
{
	struct VisitedEdge
	{
		size_t next{ 0 };
		uint32_t stepCost{ 0 };

		auto operator<=>(const VisitedEdge& other) const = default;
	};

	// Every (neighbour, cost) the grid reports for the node, sorted.
	std::vector<VisitedEdge> neighbours_of(
		const undead::GridGraph& grid,
		size_t node)
	{
		std::vector<VisitedEdge> visited;
		const auto record = [&visited](size_t next, uint32_t stepCost)
		{
			visited.push_back(VisitedEdge{ next, stepCost });
		};
		grid.for_each_neighbour(node, record);
		std::ranges::sort(visited);
		return visited;
	}
} // namespace

TEST(GridGraph, RefusesCostArrayShorterThanTheGrid)
{
	const std::vector<uint8_t> costs(7, 1);
	const auto build = [&costs]()
	{
		return undead::GridGraph{ 3, 3, costs, undead::Connectivity::FOUR };
	};
	EXPECT_THROW(build(), std::invalid_argument);
}

TEST(GridGraph, RefusesCostArrayLongerThanTheGrid)
{
	const std::vector<uint8_t> costs(10, 1);
	const auto build = [&costs]()
	{
		return undead::GridGraph{ 3, 3, costs, undead::Connectivity::FOUR };
	};
	EXPECT_THROW(build(), std::invalid_argument);
}

TEST(GridGraph, RefusesWidthTimesHeightThatOverflows)
{
	// 2^63 * 2 wraps to 0, which an unchecked product would accept as the size
	// of the empty array.
	const std::vector<uint8_t> costs{};
	const size_t halfOfSizeRange = std::numeric_limits<size_t>::max() / 2 + 1;
	const auto build = [&costs, halfOfSizeRange]()
	{
		return undead::GridGraph{ halfOfSizeRange,
			2,
			costs,
			undead::Connectivity::FOUR };
	};
	EXPECT_THROW(build(), std::invalid_argument);
}

TEST(GridGraph, AcceptsAnEmptyGrid)
{
	const std::vector<uint8_t> costs{};
	const undead::GridGraph grid{ 0, 5, costs, undead::Connectivity::FOUR };
	EXPECT_EQ(grid.node_count(), 0u);
}

TEST(GridGraph, FourWayCentreHasItsFourEdgeNeighbours)
{
	// 0 1 2
	// 3 4 5
	// 6 7 8
	const std::vector<uint8_t> costs(9, 1);
	const undead::GridGraph grid{ 3, 3, costs, undead::Connectivity::FOUR };
	const std::vector<VisitedEdge> expected{ { 1, 1 },
		{ 3, 1 },
		{ 5, 1 },
		{ 7, 1 } };
	EXPECT_EQ(neighbours_of(grid, 4), expected);
}

TEST(GridGraph, EightWayCentreAddsTheFourDiagonals)
{
	const std::vector<uint8_t> costs(9, 1);
	const undead::GridGraph grid{ 3, 3, costs, undead::Connectivity::EIGHT };
	const std::vector<VisitedEdge> expected{
		{ 0, 1 },
		{ 1, 1 },
		{ 2, 1 },
		{ 3, 1 },
		{ 5, 1 },
		{ 6, 1 },
		{ 7, 1 },
		{ 8, 1 },
	};
	EXPECT_EQ(neighbours_of(grid, 4), expected);
}

TEST(GridGraph, CornerReportsOnlyInBoundsNeighbours)
{
	const std::vector<uint8_t> costs(9, 1);
	const undead::GridGraph grid{ 3, 3, costs, undead::Connectivity::EIGHT };
	const std::vector<VisitedEdge> expected{ { 1, 1 }, { 3, 1 }, { 4, 1 } };
	EXPECT_EQ(neighbours_of(grid, 0), expected);
}

TEST(GridGraph, EastEdgeDoesNotWrapOntoTheNextRow)
{
	// 0 1 2
	// 3 4 5
	// Cell 2 is the east end of row 0; cell 3 is the west end of row 1 and is
	// one index away, but not adjacent.
	const std::vector<uint8_t> costs(6, 1);
	const undead::GridGraph fourWay{ 3, 2, costs, undead::Connectivity::FOUR };
	const std::vector<VisitedEdge> expectedFour{ { 1, 1 }, { 5, 1 } };
	EXPECT_EQ(neighbours_of(fourWay, 2), expectedFour);

	const undead::GridGraph eightWay{ 3,
		2,
		costs,
		undead::Connectivity::EIGHT };
	const std::vector<VisitedEdge> expectedEight{ { 1, 1 },
		{ 4, 1 },
		{ 5, 1 } };
	EXPECT_EQ(neighbours_of(eightWay, 2), expectedEight);
}

TEST(GridGraph, WestEdgeDoesNotWrapOntoThePreviousRow)
{
	const std::vector<uint8_t> costs(6, 1);
	const undead::GridGraph eightWay{ 3,
		2,
		costs,
		undead::Connectivity::EIGHT };
	const std::vector<VisitedEdge> expected{ { 0, 1 }, { 1, 1 }, { 4, 1 } };
	EXPECT_EQ(neighbours_of(eightWay, 3), expected);
}

TEST(GridGraph, StepCostIsTheCostOfTheCellEnteredAndWallsAreSkipped)
{
	// 1 0 2 - cell 1 is a wall.
	const std::vector<uint8_t> costs{ 1, 0, 2 };
	const undead::GridGraph grid{ 3, 1, costs, undead::Connectivity::FOUR };
	EXPECT_EQ(neighbours_of(grid, 0), std::vector<VisitedEdge>{});
	const std::vector<VisitedEdge> fromWall{ { 0, 1 }, { 2, 2 } };
	EXPECT_EQ(neighbours_of(grid, 1), fromWall);
}

TEST(GridGraph, MaxStepCostIsTheLargestByte)
{
	EXPECT_EQ(undead::GridGraph::max_step_cost(), 255u);
}
