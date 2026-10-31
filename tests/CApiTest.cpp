// undead_dijkstra_map, the C API: a call from real C code, agreement with the
// Bellman-Ford oracle, one test per status code, and the guarantee that the
// output array is untouched on every error.
#include <cstdint>
#include <limits>
#include <optional>
#include <random>
#include <vector>

#include <gtest/gtest.h>

#include "BellmanFordOracle.h"
#include "undead/undead.h"

extern "C" int c_caller_door_corridor(uint32_t* distances);

namespace
{
	// A value no search writes, so an untouched output array is recognisable.
	constexpr uint32_t UNTOUCHED = 0xDEADBEEF;

	std::vector<uint32_t> oracle_as_c(
		const std::vector<std::optional<uint64_t>>& oracle)
	{
		std::vector<uint32_t> distances;
		for (const std::optional<uint64_t>& distance : oracle)
		{
			distances.push_back(
				distance ? static_cast<uint32_t>(*distance) : UNDEAD_UNREACHED);
		}
		return distances;
	}
} // namespace

TEST(CApi, CallFromCFloodsTheDoorCorridor)
{
	std::vector<uint32_t> distances(7, UNTOUCHED);
	EXPECT_EQ(c_caller_door_corridor(distances.data()), UNDEAD_OK);
	const std::vector<uint32_t> expected{ 0, 1, 2, 3, 5, 6, 7 };
	EXPECT_EQ(distances, expected);
}

TEST(CApi, UnreachedCellHoldsTheSentinel)
{
	const std::vector<uint8_t> costs{ 1, 0, 1 };
	const std::vector<size_t> sources{ 0 };
	std::vector<uint32_t> distances(3, UNTOUCHED);
	EXPECT_EQ(
		undead_dijkstra_map(
			3,
			1,
			costs.data(),
			UNDEAD_FOUR_WAY,
			sources.data(),
			1,
			distances.data()),
		UNDEAD_OK);
	const std::vector<uint32_t> expected{ 0,
		UNDEAD_UNREACHED,
		UNDEAD_UNREACHED };
	EXPECT_EQ(distances, expected);
}

TEST(CApi, MatchesBellmanFordOnRandomGrids)
{
	for (uint32_t seed = 1; seed <= 50; ++seed)
	{
		std::mt19937 random{ seed };
		std::uniform_int_distribution<size_t> sideLength{ 1, 16 };
		const size_t width = sideLength(random);
		const size_t height = sideLength(random);
		std::uniform_int_distribution<int> cost{ 0, 255 };
		std::vector<uint8_t> costs(width * height);
		for (uint8_t& cell : costs)
		{
			cell = static_cast<uint8_t>(cost(random));
		}
		std::uniform_int_distribution<size_t> cell{ 0, width * height - 1 };
		const std::vector<size_t> sources{ cell(random), cell(random) };

		for (const bool eightWay : { false, true })
		{
			std::vector<uint32_t> distances(width * height, UNTOUCHED);
			EXPECT_EQ(
				undead_dijkstra_map(
					width,
					height,
					costs.data(),
					eightWay ? UNDEAD_EIGHT_WAY : UNDEAD_FOUR_WAY,
					sources.data(),
					sources.size(),
					distances.data()),
				UNDEAD_OK);
			const std::vector<undead_test::OracleEdge> edges =
				undead_test::grid_edges(width, height, costs, eightWay);
			EXPECT_EQ(
				distances,
				oracle_as_c(
					undead_test::bellman_ford(width * height, edges, sources)))
				<< "seed " << seed << ", eightWay " << eightWay;
		}
	}
}

TEST(CApi, EmptyGridAcceptsNullArrays)
{
	EXPECT_EQ(
		undead_dijkstra_map(
			0,
			4,
			nullptr,
			UNDEAD_FOUR_WAY,
			nullptr,
			0,
			nullptr),
		UNDEAD_OK);
}

TEST(CApi, NoSourcesAcceptsANullSourceArray)
{
	const std::vector<uint8_t> costs(2, 1);
	std::vector<uint32_t> distances(2, UNTOUCHED);
	EXPECT_EQ(
		undead_dijkstra_map(
			2,
			1,
			costs.data(),
			UNDEAD_FOUR_WAY,
			nullptr,
			0,
			distances.data()),
		UNDEAD_OK);
	const std::vector<uint32_t> expected{ UNDEAD_UNREACHED, UNDEAD_UNREACHED };
	EXPECT_EQ(distances, expected);
}

TEST(CApi, NullStepCostsOnANonEmptyGridIsRefused)
{
	const std::vector<size_t> sources{ 0 };
	std::vector<uint32_t> distances(2, UNTOUCHED);
	EXPECT_EQ(
		undead_dijkstra_map(
			2,
			1,
			nullptr,
			UNDEAD_FOUR_WAY,
			sources.data(),
			1,
			distances.data()),
		UNDEAD_ERROR_NULL_ARGUMENT);
	EXPECT_EQ(distances, std::vector<uint32_t>(2, UNTOUCHED));
}

TEST(CApi, NullDistancesOnANonEmptyGridIsRefused)
{
	const std::vector<uint8_t> costs(2, 1);
	const std::vector<size_t> sources{ 0 };
	EXPECT_EQ(
		undead_dijkstra_map(
			2,
			1,
			costs.data(),
			UNDEAD_FOUR_WAY,
			sources.data(),
			1,
			nullptr),
		UNDEAD_ERROR_NULL_ARGUMENT);
}

TEST(CApi, NullSourcesWithACountIsRefused)
{
	const std::vector<uint8_t> costs(2, 1);
	std::vector<uint32_t> distances(2, UNTOUCHED);
	EXPECT_EQ(
		undead_dijkstra_map(
			2,
			1,
			costs.data(),
			UNDEAD_FOUR_WAY,
			nullptr,
			1,
			distances.data()),
		UNDEAD_ERROR_NULL_ARGUMENT);
	EXPECT_EQ(distances, std::vector<uint32_t>(2, UNTOUCHED));
}

TEST(CApi, OverflowingGridSizeIsRefused)
{
	// 2^63 * 2 wraps to 0, which an unchecked product would read as empty.
	const std::vector<uint8_t> costs(2, 1);
	const size_t halfOfSizeRange = std::numeric_limits<size_t>::max() / 2 + 1;
	const std::vector<size_t> sources{ 0 };
	std::vector<uint32_t> distances(2, UNTOUCHED);
	EXPECT_EQ(
		undead_dijkstra_map(
			halfOfSizeRange,
			2,
			costs.data(),
			UNDEAD_FOUR_WAY,
			sources.data(),
			1,
			distances.data()),
		UNDEAD_ERROR_GRID_SIZE);
	EXPECT_EQ(distances, std::vector<uint32_t>(2, UNTOUCHED));
}

TEST(CApi, SourceOutsideTheGridIsRefused)
{
	const std::vector<uint8_t> costs(7, 1);
	const std::vector<size_t> sources{ 7 };
	std::vector<uint32_t> distances(7, UNTOUCHED);
	EXPECT_EQ(
		undead_dijkstra_map(
			7,
			1,
			costs.data(),
			UNDEAD_EIGHT_WAY,
			sources.data(),
			1,
			distances.data()),
		UNDEAD_ERROR_SOURCE_OUT_OF_RANGE);
	EXPECT_EQ(distances, std::vector<uint32_t>(7, UNTOUCHED));
}

TEST(CApi, UnknownConnectivityIsRefused)
{
	const std::vector<uint8_t> costs(2, 1);
	const std::vector<size_t> sources{ 0 };
	std::vector<uint32_t> distances(2, UNTOUCHED);
	EXPECT_EQ(
		undead_dijkstra_map(
			2,
			1,
			costs.data(),
			6,
			sources.data(),
			1,
			distances.data()),
		UNDEAD_ERROR_CONNECTIVITY);
	EXPECT_EQ(distances, std::vector<uint32_t>(2, UNTOUCHED));
}

TEST(CApi, DistanceOverflowIsRefused)
{
	// A corridor of cost-255 cells: cell k is at 255 * k, and k = 16843009 is
	// the first to reach UINT32_MAX (4294967295).
	const size_t width = 16843010;
	const std::vector<uint8_t> costs(width, 255);
	const std::vector<size_t> sources{ 0 };
	std::vector<uint32_t> distances(width, UNTOUCHED);
	EXPECT_EQ(
		undead_dijkstra_map(
			width,
			1,
			costs.data(),
			UNDEAD_FOUR_WAY,
			sources.data(),
			1,
			distances.data()),
		UNDEAD_ERROR_DISTANCE_OVERFLOW);
	EXPECT_EQ(distances.back(), UNTOUCHED);
	EXPECT_EQ(distances.front(), UNTOUCHED);
}
