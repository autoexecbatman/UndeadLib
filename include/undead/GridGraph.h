/**
 * @file GridGraph.h
 * @brief A rectangular grid of cells as a graph for DialSearch: each cell is
 * a node, and stepping onto a cell costs that cell's step cost.
 *
 * The caller owns a row-major array of uint8_t step costs, one per cell. A
 * cost of 0 means the cell cannot be entered (a wall); 1 to 255 is what it
 * costs to step onto it. The GridGraph views that array and copies nothing,
 * so the array must outlive the GridGraph. Cell (column, row) is node
 * row * width + column.
 *
 * Usage, the game's corridor with a shut door (cost 2) at column 4:
 * @code
 *   const std::vector<uint8_t> costs{ 1, 1, 1, 1, 2, 1, 1 };
 *   const undead::GridGraph corridor{ 7, 1, costs, undead::Connectivity::EIGHT };
 *   corridor.node_count();     // -> 7
 *   corridor.max_step_cost();  // -> 255, the largest cost a uint8_t holds
 *   undead::GridGraph{ 3, 3, costs, undead::Connectivity::FOUR };
 *                              // throws std::invalid_argument: 7 costs, 9 cells
 * @endcode
 */
#pragma once

#include <cstdint>
#include <limits>
#include <optional>
#include <span>
#include <stdexcept>

namespace undead
{
	/**
	 * @brief Which neighbours a cell has: the four sharing an edge, or those
	 * and the four diagonals. A diagonal step costs what a cardinal one does.
	 */
	enum class Connectivity
	{
		FOUR,
		EIGHT
	};

	/**
	 * @brief A grid of step costs, searchable by DialSearch.
	 */
	class GridGraph
	{
	private:
		size_t columnCount{ 0 };
		size_t rowCount{ 0 };
		std::span<const uint8_t> stepCosts{};
		Connectivity connectivity{ Connectivity::FOUR };

	public:
		/**
		 * @brief Views a row-major array of step costs as a grid.
		 *
		 * Example:
		 * @code
		 *   const std::vector<uint8_t> costs(12, 1);
		 *   const undead::GridGraph grid{ 4, 3, costs, undead::Connectivity::FOUR };
		 *   grid.node_count();  // -> 12
		 * @endcode
		 *
		 * @param[in] width Cells per row.
		 * @param[in] height Rows.
		 * @param[in] cellStepCosts width * height costs, row after row; 0 is a
		 * wall. Viewed, not copied: it must outlive the GridGraph.
		 * @param[in] neighbourhood Four-way or eight-way movement.
		 * @throws std::invalid_argument when the array does not hold exactly
		 * width * height costs.
		 */
		GridGraph(
			size_t width,
			size_t height,
			std::span<const uint8_t> cellStepCosts,
			Connectivity neighbourhood) :
			columnCount(width),
			rowCount(height),
			stepCosts(cellStepCosts),
			connectivity(neighbourhood)
		{
			if (cell_count(width, height) != cellStepCosts.size())
			{
				throw std::invalid_argument(
					"GridGraph: the cost array does not hold width * height cells");
			}
		}

		/**
		 * @brief width * height, or nullopt when the product does not fit in
		 * size_t.
		 *
		 * Example:
		 * @code
		 *   undead::GridGraph::cell_count(4, 3);              // -> 12
		 *   undead::GridGraph::cell_count(SIZE_MAX / 2 + 1, 2); // -> nullopt
		 * @endcode
		 */
		[[nodiscard]] static constexpr std::optional<size_t> cell_count(
			size_t width,
			size_t height) noexcept
		{
			// Division rather than width * height, which can wrap.
			if (height != 0 &&
				width > std::numeric_limits<size_t>::max() / height)
			{
				return std::nullopt;
			}
			return width * height;
		}

		/**
		 * @brief The number of cells, width * height.
		 */
		[[nodiscard]] size_t node_count() const noexcept
		{
			return stepCosts.size();
		}

		/**
		 * @brief The largest step cost any cell can have, which is the bound
		 * DialSearch::dijkstra_map needs.
		 */
		[[nodiscard]] static constexpr uint32_t max_step_cost() noexcept
		{
			return std::numeric_limits<uint8_t>::max();
		}

		/**
		 * @brief Calls visit(next, stepCost) once for each in-bounds neighbour
		 * of the cell that can be entered, with the cost of entering it.
		 *
		 * Example, a 3x1 row of costs { 1, 0, 2 } with a wall in the middle:
		 * @code
		 *   grid.for_each_neighbour(1, visit);  // visit(0, 1), then visit(2, 2)
		 *   grid.for_each_neighbour(0, visit);  // no calls: cell 1 is a wall
		 * @endcode
		 *
		 * @param[in] node A cell index in [0, node_count()).
		 * @param[in] visit Called as visit(size_t next, uint32_t stepCost).
		 */
		template <typename Visitor>
		void for_each_neighbour(size_t node, Visitor&& visit) const
		{
			const size_t row = node / columnCount;
			const size_t column = node % columnCount;
			const bool hasNorth = row > 0;
			const bool hasSouth = row + 1 < rowCount;
			const bool hasWest = column > 0;
			const bool hasEast = column + 1 < columnCount;

			// Offers one neighbour, skipping walls.
			const auto offer = [this, &visit](size_t next)
			{
				const uint8_t stepCost = stepCosts[next];
				if (stepCost != 0)
				{
					visit(next, uint32_t{ stepCost });
				}
			};

			if (hasNorth)
			{
				offer(node - columnCount);
			}
			if (hasSouth)
			{
				offer(node + columnCount);
			}
			if (hasWest)
			{
				offer(node - 1);
			}
			if (hasEast)
			{
				offer(node + 1);
			}
			if (connectivity == Connectivity::FOUR)
			{
				return;
			}
			if (hasNorth && hasWest)
			{
				offer(node - columnCount - 1);
			}
			if (hasNorth && hasEast)
			{
				offer(node - columnCount + 1);
			}
			if (hasSouth && hasWest)
			{
				offer(node + columnCount - 1);
			}
			if (hasSouth && hasEast)
			{
				offer(node + columnCount + 1);
			}
		}
	};
} // namespace undead
