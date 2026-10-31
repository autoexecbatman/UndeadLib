"""UndeadLibrary.dijkstra_map against hand-worked answers and an oracle.

Every refusal the binding makes before calling C, and every status C can
return through it, has a test reading the exception type.
"""

import random

import numpy
import pytest

import undead
from undead import Connectivity

UNREACHED = None


def bellman_ford(
    width: int,
    height: int,
    costs: bytes,
    eight_way: bool,
    sources: list[int],
) -> list[int | None]:
    """Return shortest distances by relaxing every grid edge until stable.

    Neighbours are enumerated here by offset, independently of the library.

    Example:
        bellman_ford(3, 1, bytes([1, 0, 1]), False, [0])
        # -> [0, None, None]

    """
    distances: list[int | None] = [None] * (width * height)
    for source in sources:
        distances[source] = 0
    offsets = [
        (column_offset, row_offset)
        for row_offset in (-1, 0, 1)
        for column_offset in (-1, 0, 1)
        if (column_offset, row_offset) != (0, 0)
        and (eight_way or column_offset == 0 or row_offset == 0)
    ]
    is_changed = True
    while is_changed:
        is_changed = False
        for row in range(height):
            for column in range(width):
                here = distances[row * width + column]
                if here is None:
                    continue
                for column_offset, row_offset in offsets:
                    next_column = column + column_offset
                    next_row = row + row_offset
                    if not (
                        0 <= next_column < width and 0 <= next_row < height
                    ):
                        continue
                    target = next_row * width + next_column
                    if costs[target] == 0:
                        continue
                    candidate = here + costs[target]
                    known = distances[target]
                    if known is None or candidate < known:
                        distances[target] = candidate
                        is_changed = True
    return distances


def test_door_corridor_costs_two_to_enter_the_door(
    library: undead.UndeadLibrary,
) -> None:
    """The game's corridor: floor costs 1, the shut door at column 4 is 2."""
    costs = bytes([1, 1, 1, 1, 2, 1, 1])
    assert library.dijkstra_map(7, 1, costs, Connectivity.EIGHT_WAY, [0]) == [
        0,
        1,
        2,
        3,
        5,
        6,
        7,
    ]


def test_wall_leaves_the_far_side_unreached(
    library: undead.UndeadLibrary,
) -> None:
    """A wall between the source and a cell leaves that cell None."""
    assert library.dijkstra_map(
        3, 1, bytes([1, 0, 1]), Connectivity.FOUR_WAY, [0]
    ) == [0, UNREACHED, UNREACHED]


def test_eight_way_cuts_the_corner_four_way_walks_it(
    library: undead.UndeadLibrary,
) -> None:
    """Top-left to bottom-right of a 3x3 room: four steps, or two diagonals."""
    room = bytes([1] * 9)
    assert library.dijkstra_map(3, 3, room, Connectivity.FOUR_WAY, [0])[8] == 4
    assert (
        library.dijkstra_map(3, 3, room, Connectivity.EIGHT_WAY, [0])[8] == 2
    )


def test_no_sources_leaves_every_cell_unreached(
    library: undead.UndeadLibrary,
) -> None:
    """An empty source list floods nothing."""
    assert library.dijkstra_map(
        2, 1, bytes([1, 1]), Connectivity.FOUR_WAY, []
    ) == [UNREACHED, UNREACHED]


def test_empty_grid_returns_no_distances(
    library: undead.UndeadLibrary,
) -> None:
    """A grid with no cells has no distances."""
    assert library.dijkstra_map(0, 4, b"", Connectivity.FOUR_WAY, []) == []


def test_bytearray_costs_are_accepted(library: undead.UndeadLibrary) -> None:
    """A mutable byte buffer floods like bytes."""
    costs = bytearray([1, 2, 1])
    assert library.dijkstra_map(3, 1, costs, Connectivity.FOUR_WAY, [0]) == [
        0,
        2,
        3,
    ]


def test_numpy_grid_is_read_row_after_row(
    library: undead.UndeadLibrary,
) -> None:
    """A (height, width) uint8 array is the grid, row 0 first."""
    # Row 0 is open; row 1 is a wall except its last cell, which costs 5.
    grid = numpy.array([[1, 1, 1], [0, 0, 5]], dtype=numpy.uint8)
    assert library.dijkstra_map(3, 2, grid, Connectivity.FOUR_WAY, [0]) == [
        0,
        1,
        2,
        UNREACHED,
        UNREACHED,
        7,
    ]


def test_matches_bellman_ford_on_random_grids(
    library: undead.UndeadLibrary,
) -> None:
    """Random grids of random size, costs and sources agree with the oracle."""
    for seed in range(1, 101):
        generator = random.Random(seed)
        width = generator.randint(1, 12)
        height = generator.randint(1, 12)
        costs = bytes(generator.randint(0, 255) for _ in range(width * height))
        sources = [
            generator.randrange(width * height)
            for _ in range(generator.randint(1, 3))
        ]
        for eight_way in (False, True):
            connectivity = (
                Connectivity.EIGHT_WAY if eight_way else Connectivity.FOUR_WAY
            )
            assert library.dijkstra_map(
                width, height, costs, connectivity, sources
            ) == bellman_ford(width, height, costs, eight_way, sources), (
                f"seed {seed}, eight_way {eight_way}"
            )


def test_cost_buffer_of_the_wrong_length_is_refused(
    library: undead.UndeadLibrary,
) -> None:
    """Seven costs for a 3x3 grid would let C read past the buffer."""
    with pytest.raises(ValueError, match="width \\* height"):
        library.dijkstra_map(3, 3, bytes(7), Connectivity.FOUR_WAY, [0])


def test_cost_buffer_longer_than_the_grid_is_refused(
    library: undead.UndeadLibrary,
) -> None:
    """Ten costs for a 3x3 grid is a caller mistake, refused like seven."""
    with pytest.raises(ValueError, match="width \\* height"):
        library.dijkstra_map(3, 3, bytes(10), Connectivity.FOUR_WAY, [0])


def test_costs_that_are_not_bytes_are_refused(
    library: undead.UndeadLibrary,
) -> None:
    """uint16 costs would be read as twice as many byte costs."""
    costs = numpy.ones(4, dtype=numpy.uint16)
    with pytest.raises(TypeError, match="unsigned bytes"):
        library.dijkstra_map(2, 2, costs, Connectivity.FOUR_WAY, [0])


def test_non_contiguous_costs_are_refused(
    library: undead.UndeadLibrary,
) -> None:
    """A transposed array is not row after row in memory."""
    grid = numpy.ones((3, 2), dtype=numpy.uint8).T
    with pytest.raises(TypeError, match="contiguous"):
        library.dijkstra_map(3, 2, grid, Connectivity.FOUR_WAY, [0])


def test_negative_width_is_refused(library: undead.UndeadLibrary) -> None:
    """A width of -1 would reach C as SIZE_MAX through ctypes.

    Height 0 makes the cell count 0, matching the empty buffer, so only the
    width check stands between -1 and C.
    """
    with pytest.raises(ValueError, match="^width -1 does not fit"):
        library.dijkstra_map(-1, 0, b"", Connectivity.FOUR_WAY, [])


def test_width_beyond_size_t_is_refused(
    library: undead.UndeadLibrary,
) -> None:
    """2**64 with height 0 matches an empty buffer, then wraps to 0 in C."""
    with pytest.raises(ValueError, match="width"):
        library.dijkstra_map(2**64, 0, b"", Connectivity.FOUR_WAY, [])


def test_negative_height_is_refused(library: undead.UndeadLibrary) -> None:
    """A height of -1 would reach C as SIZE_MAX through ctypes.

    Width 0 makes the cell count 0, matching the empty buffer, so only the
    height check stands between -1 and C.
    """
    with pytest.raises(ValueError, match="^height -1 does not fit"):
        library.dijkstra_map(0, -1, b"", Connectivity.FOUR_WAY, [])


def test_negative_source_is_refused(library: undead.UndeadLibrary) -> None:
    """-1 would wrap to SIZE_MAX, which C would refuse for the wrong reason."""
    with pytest.raises(IndexError, match="source"):
        library.dijkstra_map(2, 1, bytes([1, 1]), Connectivity.FOUR_WAY, [-1])


def test_source_beyond_size_t_is_refused(
    library: undead.UndeadLibrary,
) -> None:
    """2**64 would wrap to 0, a real cell, and flood from the wrong place."""
    with pytest.raises(IndexError, match="source"):
        library.dijkstra_map(
            2, 1, bytes([1, 1]), Connectivity.FOUR_WAY, [2**64]
        )


def test_source_outside_the_grid_is_refused_by_c(
    library: undead.UndeadLibrary,
) -> None:
    """Cell 7 of a seven-cell corridor; C's range check reports it."""
    with pytest.raises(IndexError, match="UNDEAD_ERROR_SOURCE_OUT_OF_RANGE"):
        library.dijkstra_map(7, 1, bytes(7), Connectivity.FOUR_WAY, [7])


def test_unknown_connectivity_is_refused_by_c(
    library: undead.UndeadLibrary,
) -> None:
    """A plain 6 where a Connectivity belongs is refused by C."""
    with pytest.raises(ValueError, match="UNDEAD_ERROR_CONNECTIVITY"):
        library.dijkstra_map(
            2,
            1,
            bytes([1, 1]),
            6,  # type: ignore[arg-type]
            [0],
        )


def test_distance_overflow_is_refused_by_c(
    library: undead.UndeadLibrary,
) -> None:
    """Cost-255 corridor: cell 16843009 is the first at UINT32_MAX."""
    width = 16843010
    with pytest.raises(OverflowError, match="UNDEAD_ERROR_DISTANCE_OVERFLOW"):
        library.dijkstra_map(
            width, 1, bytes([255]) * width, Connectivity.FOUR_WAY, [0]
        )
