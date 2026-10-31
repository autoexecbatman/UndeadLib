"""Fixtures for the api_page tests: each source collected once per session.

A C++ header takes about two seconds to parse, with the standard library
behind it, so collecting once is what keeps the suite fast.

Usage, in a test:

    def test_something(grid_graph_file: SourceFile) -> None: ...
"""

from pathlib import Path

import pytest

import api_page
from api_model import SourceFile

ROOT = Path(__file__).resolve().parents[2]
INCLUDE = ROOT / "include" / "undead"


@pytest.fixture(scope="session")
def c_api_file() -> SourceFile:
    """Return undead.h, collected as C.

    Example:
        c_api_file.path  # -> 'include/undead/undead.h'

    """
    return api_page.collect_header(INCLUDE / "undead.h", ROOT, "C API", True)


@pytest.fixture(scope="session")
def grid_graph_file() -> SourceFile:
    """Return GridGraph.h, collected as C++.

    Example:
        grid_graph_file.entries[0].name  # -> 'undead::Connectivity'

    """
    return api_page.collect_header(
        INCLUDE / "GridGraph.h", ROOT, "C++ core", False
    )


@pytest.fixture(scope="session")
def distance_map_file() -> SourceFile:
    """Return DistanceMap.h, collected as C++.

    Example:
        distance_map_file.entries[0].name  # -> 'undead::DistanceMap'

    """
    return api_page.collect_header(
        INCLUDE / "DistanceMap.h", ROOT, "C++ core", False
    )


@pytest.fixture(scope="session")
def dial_search_file() -> SourceFile:
    """Return DialSearch.h, collected as C++.

    Example:
        dial_search_file.entries[0].name  # -> 'undead::SearchGraph'

    """
    return api_page.collect_header(
        INCLUDE / "DialSearch.h", ROOT, "C++ core", False
    )


@pytest.fixture(scope="session")
def binding_file() -> SourceFile:
    """Return the Python binding, collected with ast.

    Example:
        binding_file.section  # -> 'Python binding'

    """
    return api_page.collect_python_module(
        ROOT / "bindings" / "python" / "undead" / "__init__.py", ROOT
    )


@pytest.fixture(scope="session")
def all_files() -> list[SourceFile]:
    """Return everything collect_all finds under the repository root.

    Example:
        all_files[-1].path  # -> 'bindings/js/undead.mjs'

    """
    return api_page.collect_all(ROOT)
