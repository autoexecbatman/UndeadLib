"""Python binding of UndeadLib's C API: Dijkstra maps over grids of costs.

Load the compiled library once, then flood grids with it. A grid is a
buffer of one unsigned byte per cell, row after row: 0 is a wall, 1 to 255
is what stepping onto the cell costs. Cell (column, row) is index
row * width + column, in the costs and in the distances returned.

Typical usage:

    from pathlib import Path
    import undead

    library = undead.UndeadLibrary(Path("build/bin/Release/undead_c.dll"))
    costs = bytes([1, 1, 1, 1, 2, 1, 1])  # a shut door at column 4
    library.dijkstra_map(
        7,                              # width in cells
        1,                              # height in cells
        costs,                          # bytes, bytearray or numpy uint8
        undead.Connectivity.EIGHT_WAY,  # diagonals allowed
        [0],                            # the cells the flood starts from
    )
    # -> [0, 1, 2, 3, 5, 6, 7]
"""

import ctypes
import enum
from collections.abc import Buffer, Sequence
from pathlib import Path

# Status codes from undead.h.
_OK = 0
_ERROR_NULL_ARGUMENT = 1
_ERROR_GRID_SIZE = 2
_ERROR_SOURCE_OUT_OF_RANGE = 3
_ERROR_CONNECTIVITY = 4
_ERROR_DISTANCE_OVERFLOW = 5
_ERROR_OUT_OF_MEMORY = 6
_ERROR_INTERNAL = 7

# UNDEAD_UNREACHED: the distance C writes for a cell no source reaches.
_UNREACHED = 2**32 - 1

# The largest value a C size_t holds; ctypes wraps anything outside
# [0, _SIZE_MAX] without a word.
_SIZE_MAX: int = 2 ** (8 * ctypes.sizeof(ctypes.c_size_t)) - 1

_EXCEPTION_FOR_STATUS: dict[int, tuple[type[Exception], str]] = {
    _ERROR_NULL_ARGUMENT: (RuntimeError, "UNDEAD_ERROR_NULL_ARGUMENT"),
    _ERROR_GRID_SIZE: (ValueError, "UNDEAD_ERROR_GRID_SIZE"),
    _ERROR_SOURCE_OUT_OF_RANGE: (
        IndexError,
        "UNDEAD_ERROR_SOURCE_OUT_OF_RANGE",
    ),
    _ERROR_CONNECTIVITY: (ValueError, "UNDEAD_ERROR_CONNECTIVITY"),
    _ERROR_DISTANCE_OVERFLOW: (
        OverflowError,
        "UNDEAD_ERROR_DISTANCE_OVERFLOW",
    ),
    _ERROR_OUT_OF_MEMORY: (MemoryError, "UNDEAD_ERROR_OUT_OF_MEMORY"),
    _ERROR_INTERNAL: (RuntimeError, "UNDEAD_ERROR_INTERNAL"),
}


def _raise_for_status(status: int) -> None:
    """Raise the exception a non-OK C status stands for; do nothing on OK.

    Example:
        _raise_for_status(0)  # returns None
        _raise_for_status(3)
        # raises IndexError("undead_c: UNDEAD_ERROR_SOURCE_OUT_OF_RANGE")
        _raise_for_status(99)
        # raises RuntimeError("undead_c: unknown status 99")

    """
    if status == _OK:
        return
    if status not in _EXCEPTION_FOR_STATUS:
        raise RuntimeError(f"undead_c: unknown status {status}")
    exception_type, status_name = _EXCEPTION_FOR_STATUS[status]
    raise exception_type(f"undead_c: {status_name}")


def _is_size_t(value: int) -> bool:
    """Return whether value passes into a C size_t without wrapping.

    Example:
        _is_size_t(0)      # -> True
        _is_size_t(-1)     # -> False, ctypes would make it SIZE_MAX
        _is_size_t(2**64)  # -> False on 64-bit, ctypes would make it 0

    """
    return 0 <= value <= _SIZE_MAX


class Connectivity(enum.IntEnum):
    """Which neighbours a cell has; a diagonal costs what a cardinal does."""

    FOUR_WAY = 4
    EIGHT_WAY = 8


class UndeadLibrary:
    """The loaded undead_c library."""

    def __init__(self, dll_path: Path) -> None:
        """Load undead_c from dll_path and declare its function signatures.

        Example:
            UndeadLibrary(Path("build/bin/Release/undead_c.dll"))

        Args:
            dll_path: The compiled undead_c library (undead_c.dll on Windows).

        Raises:
            OSError: The file is missing or is not a loadable library.

        """
        self._library = ctypes.CDLL(str(dll_path))
        # Without argtypes ctypes would pass every size as a 32-bit int.
        self._dijkstra_map = self._library.undead_dijkstra_map
        self._dijkstra_map.argtypes = [
            ctypes.c_size_t,
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_size_t),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_uint32),
        ]
        self._dijkstra_map.restype = ctypes.c_int

    def dijkstra_map(
        self,
        width: int,
        height: int,
        step_costs: Buffer,
        connectivity: Connectivity,
        sources: Sequence[int],
    ) -> list[int | None]:
        """Return each cell's cheapest distance from the nearest source.

        Example:
            library.dijkstra_map(
                3, 1, bytes([1, 0, 1]), Connectivity.FOUR_WAY, [0]
            )
            # -> [0, None, None]

        Args:
            width: Cells per row.
            height: Rows.
            step_costs: width * height unsigned bytes, row after row.
            connectivity: Four-way or eight-way movement.
            sources: Cell indices at distance 0, whatever they cost to enter.

        Returns:
            One distance per cell, None where no source reaches.

        Raises:
            ValueError: width or height is negative or beyond size_t, the
                costs do not hold width * height entries, or C refused
                the connectivity.
            TypeError: step_costs is not a contiguous buffer of bytes.
            IndexError: a source is negative, beyond size_t, or (from C)
                not a cell of the grid.
            OverflowError: a distance would reach UINT32_MAX.
            MemoryError: C could not allocate the search.

        """
        # Sizes are refused here because ctypes would wrap them silently.
        if not _is_size_t(width):
            raise ValueError(f"width {width} does not fit in a C size_t")
        if not _is_size_t(height):
            raise ValueError(f"height {height} does not fit in a C size_t")
        cost_view = memoryview(step_costs)
        if cost_view.format != "B":
            raise TypeError(
                "step_costs must hold unsigned bytes, "
                f"not format {cost_view.format!r}"
            )
        if not cost_view.c_contiguous:
            raise TypeError("step_costs must be contiguous, row after row")
        # C cannot see the buffer's length; this is the only check of it.
        cell_count = width * height
        if cost_view.nbytes != cell_count:
            raise ValueError(
                f"step_costs holds {cost_view.nbytes} cells, "
                f"width * height is {cell_count}"
            )
        for source in sources:
            if not _is_size_t(source):
                raise IndexError(f"source {source} does not fit in a size_t")

        # Copied, so a read-only bytes object can be handed to C.
        cost_array = (ctypes.c_uint8 * cell_count).from_buffer_copy(cost_view)
        source_array = (ctypes.c_size_t * len(sources))(*sources)
        distance_array = (ctypes.c_uint32 * cell_count)()
        status = self._dijkstra_map(
            width,
            height,
            cost_array,
            int(connectivity),
            source_array,
            len(sources),
            distance_array,
        )
        _raise_for_status(status)
        return [
            None if distance == _UNREACHED else distance
            for distance in distance_array
        ]
