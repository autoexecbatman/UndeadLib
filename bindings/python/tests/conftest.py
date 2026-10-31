"""Fixtures for the binding's tests: the loaded library.

The DLL path is configuration, set by ctest from $<TARGET_FILE:undead_c>.
To run by hand from bindings/python:

    $env:UNDEAD_C_DLL = "D:/repo/UndeadLib/build/bin/Release/undead_c.dll"
    python -m pytest
"""

import os
from pathlib import Path

import pytest

import undead


@pytest.fixture(scope="session")
def library() -> undead.UndeadLibrary:
    """Load the undead_c library named by the UNDEAD_C_DLL variable.

    Example:
        def test_something(library: undead.UndeadLibrary) -> None: ...

    Raises:
        RuntimeError: UNDEAD_C_DLL is not set, so there is nothing to test.

    """
    dll_path = os.environ.get("UNDEAD_C_DLL")
    if dll_path is None:
        raise RuntimeError(
            "UNDEAD_C_DLL is not set; point it at the built undead_c.dll"
        )
    return undead.UndeadLibrary(Path(dll_path))
