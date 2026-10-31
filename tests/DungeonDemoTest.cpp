// The dungeon demo's game rules, each checked against a map worked out by
// hand from docs/demo-contract.md.
#include <cstdint>
#include <optional>
#include <stdexcept>
#include <string>
#include <vector>

#include <gtest/gtest.h>

#include "DungeonDemo.h"

namespace
{
	// One turn of monster movement on a map, drawn back as text.
	std::string after_one_turn(const std::string& map)
	{
		undead_demo::Dungeon dungeon = undead_demo::parse_dungeon(map);
		undead_demo::advance_monsters(dungeon);
		return undead_demo::render_dungeon(dungeon);
	}

	// What run_until_caught reported, and every frame its observer saw.
	struct RecordedRun
	{
		std::optional<size_t> turns{};
		std::vector<std::string> frames{};
	};

	// Runs the chase, recording each turn as "turn:map".
	RecordedRun run_and_record(undead_demo::Dungeon& dungeon, size_t maxTurns)
	{
		RecordedRun run{};
		const auto record =
			[&run](size_t turn, const undead_demo::Dungeon& seen)
		{
			run.frames.push_back(
				std::to_string(turn) + ":" + undead_demo::render_dungeon(seen));
		};
		run.turns = undead_demo::run_until_caught(dungeon, maxTurns, record);
		return run;
	}
} // namespace

TEST(DungeonDemo, ParsesCostsPlayerAndMonsters)
{
	const undead_demo::Dungeon dungeon =
		undead_demo::parse_dungeon("#.+\n@M.\n");
	EXPECT_EQ(dungeon.width, 3u);
	EXPECT_EQ(dungeon.height, 2u);
	const std::vector<uint8_t> expectedCosts{ 0, 1, 2, 1, 1, 1 };
	EXPECT_EQ(dungeon.stepCosts, expectedCosts);
	EXPECT_EQ(dungeon.player, 3u);
	const std::vector<size_t> expectedMonsters{ 4 };
	EXPECT_EQ(dungeon.monsters, expectedMonsters);
}

TEST(DungeonDemo, RenderGivesTheParsedMapBack)
{
	const std::string map = "#####\n#@+M#\n#...#\n#####\n";
	EXPECT_EQ(
		undead_demo::render_dungeon(undead_demo::parse_dungeon(map)),
		map);
}

TEST(DungeonDemo, RefusesRaggedRows)
{
	const auto parse = []()
	{
		return undead_demo::parse_dungeon("@..\n..\n");
	};
	EXPECT_THROW(parse(), std::invalid_argument);
}

TEST(DungeonDemo, RefusesAnUnknownCharacter)
{
	const auto parse = []()
	{
		return undead_demo::parse_dungeon("@x\n");
	};
	EXPECT_THROW(parse(), std::invalid_argument);
}

TEST(DungeonDemo, RefusesAMapWithNoPlayer)
{
	const auto parse = []()
	{
		return undead_demo::parse_dungeon("..M\n");
	};
	EXPECT_THROW(parse(), std::invalid_argument);
}

TEST(DungeonDemo, RefusesAMapWithTwoPlayers)
{
	const auto parse = []()
	{
		return undead_demo::parse_dungeon("@.@\n");
	};
	EXPECT_THROW(parse(), std::invalid_argument);
}

TEST(DungeonDemo, RefusesALastRowWithoutANewline)
{
	const auto parse = []()
	{
		return undead_demo::parse_dungeon("@.M\n..M");
	};
	EXPECT_THROW(parse(), std::invalid_argument);
}

TEST(DungeonDemo, OnATieTheFirstNeighbourOfferedWins)
{
	// West, north-west and south-west of the monster are all 1 from the
	// player; GridGraph offers west first.
	EXPECT_EQ(after_one_turn("...\n@.M\n...\n"), "...\n@M.\n...\n");
}

TEST(DungeonDemo, MonsterDoesNotSidestepToACellNoNearer)
{
	// The free cell below the monster is also beside the player.
	EXPECT_EQ(after_one_turn("@M\n..\n"), "@M\n..\n");
}

TEST(DungeonDemo, MonstersMoveInReadingOrderWhateverTheListOrder)
{
	// Listed back to front, the far monster would move first, find the cell
	// ahead taken, and stay.
	undead_demo::Dungeon dungeon = undead_demo::parse_dungeon("@..MM\n");
	dungeon.monsters = { 4, 3 };
	undead_demo::advance_monsters(dungeon);
	EXPECT_EQ(undead_demo::render_dungeon(dungeon), "@.MM.\n");
}

TEST(DungeonDemo, MonsterWalksDownhillAlongACorridor)
{
	EXPECT_EQ(after_one_turn("@...M\n"), "@..M.\n");
}

TEST(DungeonDemo, MonsterGoesRoundTheDoorWhenThatIsCheaper)
{
	// Through the door (cost 2) the player is 3 away; round by the floor
	// below, the cell south-west of the monster is 1 away. With the door at
	// cost 1 the monster would take the door, the first neighbour at 1.
	const std::string map = "#####\n#@+M#\n#...#\n#####\n";
	EXPECT_EQ(after_one_turn(map), "#####\n#@+.#\n#.M.#\n#####\n");
}

TEST(DungeonDemo, MonstersMoveInReadingOrderIntoVacatedCells)
{
	// The nearer monster moves first, and the second takes the cell it left.
	EXPECT_EQ(after_one_turn("@..MM\n"), "@.MM.\n");
}

TEST(DungeonDemo, MonsterBesideThePlayerStaysAndBlocksTheOneBehind)
{
	EXPECT_EQ(after_one_turn("@MM\n"), "@MM\n");
}

TEST(DungeonDemo, MonsterWithNoPathStays)
{
	EXPECT_EQ(after_one_turn("@#M\n"), "@#M\n");
}

TEST(DungeonDemo, CaughtMeansEveryMonsterIsBesideThePlayer)
{
	EXPECT_TRUE(undead_demo::is_caught(undead_demo::parse_dungeon("@M\n")));
	EXPECT_FALSE(undead_demo::is_caught(undead_demo::parse_dungeon("@M.M\n")));
	// Diagonal counts as beside.
	EXPECT_TRUE(undead_demo::is_caught(undead_demo::parse_dungeon("@.\n.M\n")));
}

TEST(DungeonDemo, CorridorChaseTakesThreeTurnsAndShowsEach)
{
	// M at column 4 reaches column 1, beside the player, on the third turn;
	// the observer sees turn 0 before any move and every turn after.
	undead_demo::Dungeon dungeon = undead_demo::parse_dungeon("@...M\n");
	const RecordedRun run = run_and_record(dungeon, 10);
	EXPECT_EQ(run.turns, 3u);
	const std::vector<std::string> expected{
		"0:@...M\n",
		"1:@..M.\n",
		"2:@.M..\n",
		"3:@M...\n",
	};
	EXPECT_EQ(run.frames, expected);
}

TEST(DungeonDemo, AlreadyCaughtTakesNoTurns)
{
	undead_demo::Dungeon dungeon = undead_demo::parse_dungeon("@M\n");
	const RecordedRun run = run_and_record(dungeon, 10);
	EXPECT_EQ(run.turns, 0u);
	EXPECT_EQ(run.frames.size(), 1u);
}

TEST(DungeonDemo, TheTurnLimitIsShownButNotPlayedPast)
{
	// The corridor needs 3 turns; with a limit of 2 the monster has moved
	// exactly twice when the run gives up.
	undead_demo::Dungeon dungeon = undead_demo::parse_dungeon("@...M\n");
	const RecordedRun run = run_and_record(dungeon, 2);
	EXPECT_EQ(run.turns, std::nullopt);
	EXPECT_EQ(undead_demo::render_dungeon(dungeon), "@.M..\n");
}

TEST(DungeonDemo, UnreachablePlayerHitsTheTurnLimit)
{
	// Turns 0 to 5 are each shown, and no turn catches the player.
	undead_demo::Dungeon dungeon = undead_demo::parse_dungeon("@#M\n");
	const RecordedRun run = run_and_record(dungeon, 5);
	EXPECT_EQ(run.turns, std::nullopt);
	EXPECT_EQ(run.frames.size(), 6u);
}
