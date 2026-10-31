// The dungeon demo: three monsters chase the player through a small dungeon,
// each walking down a Dijkstra map UndeadLib floods from the player every
// turn. Prints every turn's map, and exits 0 once every monster stands beside
// the player, or 1 if the turn limit passes first.
//
// Usage, after building:
//   build\bin\Release\dungeon_demo.exe
//   // prints "Turn 0" ... "Turn N" with a map each, then "Caught after N turns."
#include <array>
#include <cstdio>
#include <optional>
#include <string>
#include <string_view>

#include "DungeonDemo.h"

namespace
{
	// Three monsters: one in the west room, which leaves through the door
	// since that is still its cheapest way out at cost 2; one in the
	// south-west corner, which comes along the bottom corridor; and one in
	// the east room, which walks straight up.
	constexpr std::array<std::string_view, 8> DUNGEON_ROWS{
		"##############",
		"#M...#.......#",
		"#....+...@...#",
		"#....#.......#",
		"#.####...M...#",
		"#............#",
		"#M...........#",
		"##############",
	};

	// Far more turns than the map needs, so reaching it means a broken rule.
	constexpr size_t TURN_LIMIT = 40;
} // namespace

int main()
{
	// The rows become the map text parse_dungeon reads, a newline after each.
	std::string map;
	for (const std::string_view row : DUNGEON_ROWS)
	{
		map += row;
		map += '\n';
	}
	undead_demo::Dungeon dungeon = undead_demo::parse_dungeon(map);

	// Every turn is printed as it stands, before the monsters move.
	const auto print_turn = [](size_t turn, const undead_demo::Dungeon& seen)
	{
		std::printf(
			"Turn %zu\n%s\n",
			turn,
			undead_demo::render_dungeon(seen).c_str());
	};
	const std::optional<size_t> turns =
		undead_demo::run_until_caught(dungeon, TURN_LIMIT, print_turn);

	if (!turns)
	{
		std::printf("Not caught after %zu turns.\n", TURN_LIMIT);
		return 1;
	}
	std::printf("Caught after %zu turns.\n", *turns);
	return 0;
}
