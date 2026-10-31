/**
 * @file DungeonDemo.h
 * @brief The game side of the dungeon demo: an ASCII map, and monsters that
 * walk toward the player down a Dijkstra map from UndeadLib.
 *
 * The map is rows of: `#` wall, `.` floor, `+` shut door (step cost 2), `@`
 * the player, `M` a monster, each row ending in a newline. Every turn the
 * map is flooded from the player and each monster, in reading order, steps
 * to its neighbour nearest the player. UndeadLib does the flood and names
 * the neighbours; nothing here searches.
 *
 * Usage:
 * @code
 *   undead_demo::Dungeon dungeon = undead_demo::parse_dungeon("@...M\n");
 *   undead_demo::advance_monsters(dungeon);
 *   undead_demo::render_dungeon(dungeon);   // -> "@..M.\n"
 *   undead_demo::is_caught(dungeon);        // -> false, it is at column 3
 *   const auto print_turn = [](size_t turn, const undead_demo::Dungeon& seen)
 *   {
 *       std::printf("%zu\n%s", turn, undead_demo::render_dungeon(seen).c_str());
 *   };
 *   undead_demo::run_until_caught(dungeon, 10, print_turn);  // -> 2
 *   undead_demo::parse_dungeon("@x\n");
 *   // throws std::invalid_argument: 'x' is not a map character
 * @endcode
 */
#pragma once

#include <algorithm>
#include <cstdint>
#include <functional>
#include <optional>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

#include "undead/DialSearch.h"
#include "undead/DistanceMap.h"
#include "undead/GridGraph.h"

namespace undead_demo
{
	/**
	 * @brief A parsed map: step costs per cell, the player and the monsters.
	 *
	 * Cells are numbered row * width + column. The player and the monsters
	 * stand on floor, so their cells cost 1.
	 */
	struct Dungeon
	{
		size_t width{ 0 };
		size_t height{ 0 };
		std::vector<uint8_t> stepCosts{};
		size_t player{ 0 };
		std::vector<size_t> monsters{};
	};

	/** Step costs the map's terrain characters stand for. */
	inline constexpr uint8_t WALL_COST = 0;
	inline constexpr uint8_t FLOOR_COST = 1;
	inline constexpr uint8_t DOOR_COST = 2;

	/**
	 * @brief Parses an ASCII map into a Dungeon.
	 *
	 * Example:
	 * @code
	 *   undead_demo::parse_dungeon("#.+\n@M.\n").stepCosts;
	 *   // -> { 0, 1, 2, 1, 1, 1 }; player 3, monsters { 4 }
	 * @endcode
	 *
	 * @param[in] map Rows of map characters, each ending in a newline.
	 * @throws std::invalid_argument when rows differ in length, a character
	 * is not one of `#.+@M`, or the map has no player or more than one.
	 */
	[[nodiscard]] inline Dungeon parse_dungeon(std::string_view map)
	{
		Dungeon dungeon{};
		std::optional<size_t> player{};
		size_t column = 0;

		for (const char cell : map)
		{
			// A newline closes a row, and every row must match the first.
			if (cell == '\n')
			{
				if (dungeon.height == 0)
				{
					dungeon.width = column;
				}
				else if (column != dungeon.width)
				{
					throw std::invalid_argument(
						"parse_dungeon: rows differ in length");
				}
				++dungeon.height;
				column = 0;
				continue;
			}

			const size_t index = dungeon.stepCosts.size();
			switch (cell)
			{
			case '#':
			{
				dungeon.stepCosts.push_back(WALL_COST);
				break;
			}
			case '.':
			{
				dungeon.stepCosts.push_back(FLOOR_COST);
				break;
			}
			case '+':
			{
				dungeon.stepCosts.push_back(DOOR_COST);
				break;
			}
			case '@':
			{
				if (player)
				{
					throw std::invalid_argument(
						"parse_dungeon: the map has two players");
				}
				player = index;
				dungeon.stepCosts.push_back(FLOOR_COST);
				break;
			}
			case 'M':
			{
				dungeon.monsters.push_back(index);
				dungeon.stepCosts.push_back(FLOOR_COST);
				break;
			}
			default:
			{
				throw std::invalid_argument(
					"parse_dungeon: a character is not one of #.+@M");
			}
			}
			++column;
		}

		// A last row without its newline is unfinished, not a shorter row.
		if (column != 0)
		{
			throw std::invalid_argument(
				"parse_dungeon: the last row has no newline");
		}
		if (!player)
		{
			throw std::invalid_argument("parse_dungeon: the map has no player");
		}
		dungeon.player = *player;
		return dungeon;
	}

	/**
	 * @brief Draws a Dungeon back as the ASCII map it was parsed from.
	 *
	 * Example:
	 * @code
	 *   undead_demo::render_dungeon(undead_demo::parse_dungeon("@.M\n"));
	 *   // -> "@.M\n"
	 * @endcode
	 */
	[[nodiscard]] inline std::string render_dungeon(const Dungeon& dungeon)
	{
		std::string map;
		for (size_t row = 0; row < dungeon.height; ++row)
		{
			for (size_t column = 0; column < dungeon.width; ++column)
			{
				const size_t index = row * dungeon.width + column;
				const uint8_t cost = dungeon.stepCosts[index];
				// The player and the monsters are drawn over the floor.
				if (index == dungeon.player)
				{
					map += '@';
				}
				else if (
					std::ranges::find(dungeon.monsters, index) !=
					dungeon.monsters.end())
				{
					map += 'M';
				}
				else if (cost == WALL_COST)
				{
					map += '#';
				}
				else if (cost == DOOR_COST)
				{
					map += '+';
				}
				else
				{
					map += '.';
				}
			}
			map += '\n';
		}
		return map;
	}

	/**
	 * @brief Moves every monster one step toward the player.
	 *
	 * The map is flooded from the player through UndeadLib. Each monster, in
	 * reading order, steps to the neighbour GridGraph offers with the lowest
	 * distance, if that is lower than its own; the first such neighbour wins
	 * a tie. A monster never steps onto the player or another monster, so a
	 * monster already beside the player stays where it is.
	 *
	 * Example:
	 * @code
	 *   undead_demo::Dungeon dungeon = undead_demo::parse_dungeon("@..MM\n");
	 *   undead_demo::advance_monsters(dungeon);
	 *   undead_demo::render_dungeon(dungeon);  // -> "@.MM.\n"
	 * @endcode
	 */
	inline void advance_monsters(Dungeon& dungeon)
	{
		const undead::GridGraph grid{
			dungeon.width,
			dungeon.height,
			dungeon.stepCosts,
			undead::Connectivity::EIGHT,
		};
		const std::vector<size_t> sources{ dungeon.player };
		const undead::DistanceMap toPlayer = undead::DialSearch::dijkstra_map(
			grid,
			sources,
			undead::GridGraph::max_step_cost());

		// Reading order is the order of cell numbers.
		std::ranges::sort(dungeon.monsters);
		for (size_t& monster : dungeon.monsters)
		{
			const std::optional<uint32_t> here = toPlayer.distance(monster);
			std::optional<size_t> bestCell{};
			std::optional<uint32_t> bestDistance{};

			// The nearest free neighbour, first found on a tie.
			const auto consider =
				[&](size_t next, [[maybe_unused]] uint32_t stepCost)
			{
				const bool isTaken = next == dungeon.player ||
					std::ranges::find(dungeon.monsters, next) !=
						dungeon.monsters.end();
				const std::optional<uint32_t> distance =
					toPlayer.distance(next);
				if (isTaken || !distance)
				{
					return;
				}
				if (!bestDistance || *distance < *bestDistance)
				{
					bestCell = next;
					bestDistance = distance;
				}
			};
			grid.for_each_neighbour(monster, consider);

			// Only a step that gets nearer is taken.
			if (bestCell && here && *bestDistance < *here)
			{
				monster = *bestCell;
			}
		}
	}

	/**
	 * @brief Whether every monster stands next to the player, diagonals
	 * included.
	 *
	 * Example:
	 * @code
	 *   undead_demo::is_caught(undead_demo::parse_dungeon("@.\n.M\n"));
	 *   // -> true
	 * @endcode
	 */
	[[nodiscard]] inline bool is_caught(const Dungeon& dungeon)
	{
		const size_t playerRow = dungeon.player / dungeon.width;
		const size_t playerColumn = dungeon.player % dungeon.width;

		// One cell apart on both axes, measured without unsigned underflow.
		const auto is_beside = [&](size_t monster)
		{
			const size_t row = monster / dungeon.width;
			const size_t column = monster % dungeon.width;
			const size_t rowGap =
				row > playerRow ? row - playerRow : playerRow - row;
			const size_t columnGap = column > playerColumn ?
				column - playerColumn :
				playerColumn - column;
			return rowGap <= 1 && columnGap <= 1;
		};
		return std::ranges::all_of(dungeon.monsters, is_beside);
	}

	/**
	 * @brief Called with each turn's number and the dungeon as it stands.
	 */
	using TurnObserver = std::function<void(size_t, const Dungeon&)>;

	/**
	 * @brief Advances turns until the player is caught, up to a limit, and
	 * reports how many it took.
	 *
	 * onTurn sees turn 0 before any move, then every turn after a move, so a
	 * run that takes N turns calls it N + 1 times.
	 *
	 * Example:
	 * @code
	 *   undead_demo::Dungeon dungeon = undead_demo::parse_dungeon("@...M\n");
	 *   undead_demo::run_until_caught(dungeon, 10, print_turn);  // -> 3
	 *   undead_demo::Dungeon walled = undead_demo::parse_dungeon("@#M\n");
	 *   undead_demo::run_until_caught(walled, 5, print_turn);    // -> nullopt
	 *   // print_turn is the observer from the file comment
	 * @endcode
	 *
	 * @param[in,out] dungeon Moved turn by turn.
	 * @param[in] maxTurns The most turns to play.
	 * @param[in] onTurn Shown each turn, for printing or recording.
	 * @returns The turns it took, or nullopt if maxTurns passed first.
	 */
	[[nodiscard]] inline std::optional<size_t> run_until_caught(
		Dungeon& dungeon,
		size_t maxTurns,
		const TurnObserver& onTurn)
	{
		for (size_t turn = 0; turn <= maxTurns; ++turn)
		{
			onTurn(turn, dungeon);
			if (is_caught(dungeon))
			{
				return turn;
			}
			// The last turn is shown but not played past.
			if (turn < maxTurns)
			{
				advance_monsters(dungeon);
			}
		}
		return std::nullopt;
	}
} // namespace undead_demo
