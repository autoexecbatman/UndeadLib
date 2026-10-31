"""api_page: the comment parsers, what each source yields, the gate, the page.

Expected declarations are named from the headers and the module as written,
so a declaration the walk loses, or one it invents, fails a test by name.
"""

import shutil
import subprocess
from pathlib import Path

import api_page
from api_model import DocBlock, DocPart, Entry, Field, SourceFile

ROOT = Path(__file__).resolve().parents[2]
INCLUDE = ROOT / "include" / "undead"
BINDING = ROOT / "bindings" / "python" / "undead" / "__init__.py"


def entry_named(source: SourceFile, name: str) -> Entry:
    """Return the one entry with that name, failing unless there is one.

    Example:
        entry_named(grid_file, "GridGraph::node_count").kind  # -> "method"

    """
    matches = [entry for entry in source.entries if entry.name == name]
    assert len(matches) == 1, (
        f"{name}: {len(matches)} entries in {source.path}; "
        f"names are {[entry.name for entry in source.entries]}"
    )
    return matches[0]


def parts_of_kind(block: DocBlock, kind: str) -> list[DocPart]:
    """Return the parts of a block that have the given kind.

    Example:
        parts_of_kind(block, "code")  # -> the example blocks, in order

    """
    return [part for part in block.parts if part.kind == kind]


# The comment parsers.


def test_doxygen_comment_splits_prose_code_and_tags() -> None:
    """Prose, a @code block, @param, @returns and @throws become parts."""
    raw = "\n".join(
        [
            "/**",
            " * @brief Floods the graph.",
            " * A source is at distance 0.",
            " *",
            " * @code",
            " *   map.distance(4);  // -> 5",
            " * @endcode",
            " *",
            " * @param[in] graph The graph",
            " * to flood.",
            " * @returns The distance map.",
            " * @throws std::out_of_range when a source is not a node.",
            " */",
        ]
    )
    block = api_page.parse_doxygen_comment(raw)
    assert [part.kind for part in block.parts] == [
        "text",
        "code",
        "fields",
        "fields",
        "fields",
    ]
    assert (
        block.parts[0].text == "Floods the graph. A source is at distance 0."
    )
    assert block.parts[1].text == "map.distance(4);  // -> 5"
    assert block.parts[2].title == "Parameters"
    assert block.parts[2].fields == [Field("graph", "The graph to flood.")]
    assert block.parts[3].title == "Returns"
    assert block.parts[3].fields == [Field("", "The distance map.")]
    assert block.parts[4].title == "Throws"
    assert block.parts[4].fields == [
        Field("std::out_of_range", "when a source is not a node.")
    ]


def test_doxygen_code_keeps_its_indentation() -> None:
    """Lines inside @code keep their indentation relative to each other."""
    raw = "/**\n * @code\n *   call(\n *       argument);\n * @endcode\n */"
    block = api_page.parse_doxygen_comment(raw)
    assert parts_of_kind(block, "code")[0].text == "call(\n    argument);"


def test_doxygen_file_tag_is_dropped() -> None:
    """@file names the file, which the page already shows."""
    raw = "/**\n * @file undead.h\n * @brief The C API.\n */"
    block = api_page.parse_doxygen_comment(raw)
    assert [part.text for part in block.parts] == ["The C API."]


def test_one_line_doxygen_comment_is_prose() -> None:
    """A single-line /** */ comment is its own prose."""
    block = api_page.parse_doxygen_comment(
        "/** A required pointer was NULL. */"
    )
    assert [part.text for part in block.parts] == [
        "A required pointer was NULL."
    ]


def test_google_docstring_splits_sections() -> None:
    """Summary, Example, Args, Returns and Raises become parts."""
    text = "\n".join(
        [
            "Return each cell's distance.",
            "",
            "Example:",
            "    library.dijkstra_map(3, 1)",
            "    # -> [0, None, None]",
            "",
            "Args:",
            "    width: Cells per row.",
            "    sources: Cell indices",
            "        at distance 0.",
            "",
            "Returns:",
            "    One distance per cell.",
            "",
            "Raises:",
            "    ValueError: width is negative.",
        ]
    )
    block = api_page.parse_google_docstring(text)
    assert [part.kind for part in block.parts] == [
        "text",
        "code",
        "fields",
        "fields",
        "fields",
    ]
    assert block.parts[0].text == "Return each cell's distance."
    assert block.parts[1].text == (
        "library.dijkstra_map(3, 1)\n# -> [0, None, None]"
    )
    assert block.parts[2].title == "Parameters"
    assert block.parts[2].fields == [
        Field("width", "Cells per row."),
        Field("sources", "Cell indices at distance 0."),
    ]
    assert block.parts[3].fields == [Field("", "One distance per cell.")]
    assert block.parts[4].title == "Raises"
    assert block.parts[4].fields == [Field("ValueError", "width is negative.")]


def test_google_indented_block_without_a_section_is_code() -> None:
    """A module docstring's indented usage block renders as code."""
    text = (
        "Summary.\n\nTypical usage:\n\n    import undead\n    undead.call()\n"
    )
    block = api_page.parse_google_docstring(text)
    assert [part.kind for part in block.parts] == ["text", "text", "code"]
    assert block.parts[2].text == "import undead\nundead.call()"


# What each source yields.


def test_c_api_lists_the_function_the_enums_and_the_macro(
    c_api_file: SourceFile,
) -> None:
    """undead.h: undead_dijkstra_map, both enums, UNDEAD_UNREACHED."""
    source = c_api_file
    names = [entry.name for entry in source.entries]
    assert sorted(names) == sorted(
        [
            "UNDEAD_UNREACHED",
            "enum UNDEAD_OK .. UNDEAD_ERROR_INTERNAL",
            "enum UNDEAD_FOUR_WAY .. UNDEAD_EIGHT_WAY",
            "undead_dijkstra_map",
        ]
    )
    assert source.path == "include/undead/undead.h"
    assert source.overview is not None


def test_c_status_constants_carry_their_own_comments(
    c_api_file: SourceFile,
) -> None:
    """Each status code is a member, with its comment where it has one."""
    source = c_api_file
    status = entry_named(source, "enum UNDEAD_OK .. UNDEAD_ERROR_INTERNAL")
    members = {member.name: member.text for member in status.members}
    assert list(members)[0] == "UNDEAD_OK = 0"
    assert members["UNDEAD_ERROR_GRID_SIZE = 2"] == (
        "width * height does not fit in size_t."
    )


def test_c_function_signature_is_the_whole_declaration(
    c_api_file: SourceFile,
) -> None:
    """The C function's signature names every parameter and no export macro."""
    source = c_api_file
    signature = entry_named(source, "undead_dijkstra_map").signature
    assert signature.startswith("int undead_dijkstra_map(")
    assert "uint32_t* distances)" in signature
    assert "UNDEAD_API" not in signature


def test_grid_graph_lists_public_members_only(
    grid_graph_file: SourceFile,
) -> None:
    """GridGraph.h: the enum, the class, its public members, no private."""
    source = grid_graph_file
    assert sorted(entry.name for entry in source.entries) == sorted(
        [
            "undead::Connectivity",
            "undead::GridGraph",
            "undead::GridGraph::GridGraph",
            "undead::GridGraph::cell_count",
            "undead::GridGraph::node_count",
            "undead::GridGraph::max_step_cost",
            "undead::GridGraph::for_each_neighbour",
        ]
    )
    connectivity = entry_named(source, "undead::Connectivity")
    assert [member.name for member in connectivity.members] == [
        "FOUR",
        "EIGHT",
    ]


def test_constructor_signature_stops_before_the_initializer_list(
    grid_graph_file: SourceFile,
) -> None:
    """The constructor's signature ends at its closing parenthesis."""
    source = grid_graph_file
    signature = entry_named(source, "undead::GridGraph::GridGraph").signature
    assert signature.endswith("Connectivity neighbourhood)")
    assert "columnCount" not in signature


def test_method_signature_keeps_const_noexcept_and_drops_the_body(
    grid_graph_file: SourceFile,
) -> None:
    """A const noexcept method keeps both qualifiers and loses its body."""
    source = grid_graph_file
    signature = entry_named(source, "undead::GridGraph::node_count").signature
    assert signature == "[[nodiscard]] size_t node_count() const noexcept"


def test_distance_map_hides_private_members_and_the_forward_declaration(
    distance_map_file: SourceFile,
) -> None:
    """DistanceMap.h lists the class and its two public methods only."""
    source = distance_map_file
    assert sorted(entry.name for entry in source.entries) == sorted(
        [
            "undead::DistanceMap",
            "undead::DistanceMap::node_count",
            "undead::DistanceMap::distance",
        ]
    )


def test_dial_search_lists_the_concept_class_and_template(
    dial_search_file: SourceFile,
) -> None:
    """DialSearch.h: the concept, the class, the function template."""
    source = dial_search_file
    assert sorted(entry.name for entry in source.entries) == sorted(
        [
            "undead::SearchGraph",
            "undead::DialSearch",
            "undead::DialSearch::dijkstra_map",
        ]
    )
    signature = entry_named(
        source, "undead::DialSearch::dijkstra_map"
    ).signature
    assert signature.startswith("template <SearchGraph Graph>")
    assert signature.endswith("uint32_t maxStepCost)")
    assert "{" not in signature


def test_header_comment_parts_are_parsed(
    distance_map_file: SourceFile,
) -> None:
    """A header method's doc arrives parsed, with its @throws as fields."""
    source = distance_map_file
    doc = entry_named(source, "undead::DistanceMap::distance").doc
    assert doc is not None
    throws = [part for part in doc.parts if part.title == "Throws"]
    assert throws[0].fields[0].name == "std::out_of_range"


def test_python_binding_lists_public_api_only(
    binding_file: SourceFile,
) -> None:
    """The binding: Connectivity, UndeadLibrary, two methods, no helpers."""
    source = binding_file
    assert sorted(entry.name for entry in source.entries) == sorted(
        [
            "Connectivity",
            "UndeadLibrary",
            "UndeadLibrary.__init__",
            "UndeadLibrary.dijkstra_map",
        ]
    )
    assert source.section == "Python binding"
    assert source.path == "bindings/python/undead/__init__.py"
    connectivity = entry_named(source, "Connectivity")
    assert [member.name for member in connectivity.members] == [
        "FOUR_WAY = 4",
        "EIGHT_WAY = 8",
    ]


def test_entries_are_in_reading_order(c_api_file: SourceFile) -> None:
    """undead.h lists the macro first, as it is declared first in the file.

    The macro is collected after the declarations, so only the sort puts it
    back where the reader meets it.
    """
    assert [entry.name for entry in c_api_file.entries] == [
        "UNDEAD_UNREACHED",
        "enum UNDEAD_OK .. UNDEAD_ERROR_INTERNAL",
        "enum UNDEAD_FOUR_WAY .. UNDEAD_EIGHT_WAY",
        "undead_dijkstra_map",
    ]


def test_long_python_signature_breaks_one_parameter_per_line(
    binding_file: SourceFile,
) -> None:
    """A def line too long for one line lists a parameter per line."""
    signature = entry_named(
        binding_file, "UndeadLibrary.dijkstra_map"
    ).signature
    assert signature == "\n".join(
        [
            "def dijkstra_map(",
            "    self,",
            "    width: int,",
            "    height: int,",
            "    step_costs: Buffer,",
            "    connectivity: Connectivity,",
            "    sources: Sequence[int],",
            ") -> list[int | None]",
        ]
    )


def test_c_function_documents_each_parameter(c_api_file: SourceFile) -> None:
    """undead_dijkstra_map's comment has a parameter field per argument."""
    doc = entry_named(c_api_file, "undead_dijkstra_map").doc
    assert doc is not None
    parameters = parts_of_kind(doc, "fields")[0]
    assert parameters.title == "Parameters"
    assert [field.name for field in parameters.fields] == [
        "width",
        "height",
        "step_costs",
        "connectivity",
        "sources",
        "source_count",
        "distances",
    ]


def test_python_signature_is_the_def_line(binding_file: SourceFile) -> None:
    """A method's signature is its def line with annotations, no body."""
    source = binding_file
    signature = entry_named(source, "UndeadLibrary.__init__").signature
    assert signature == "def __init__(self, dll_path: Path) -> None"


# The coverage gate.


def test_gate_names_undocumented_declarations(tmp_path: Path) -> None:
    """An uncommented C function and Python function are both named."""
    header = tmp_path / "bare.h"
    header.write_text(
        "/** A header. */\n#pragma once\nint bare_call(int value);\n",
        encoding="utf-8",
    )
    module = tmp_path / "bare.py"
    module.write_text(
        '"""A module."""\n\n\ndef bare_call() -> None:\n    pass\n',
        encoding="utf-8",
    )
    files = [
        api_page.collect_header(header, tmp_path, "C API", True),
        api_page.collect_python_module(module, tmp_path),
    ]
    assert api_page.undocumented(files) == [
        "bare.h: bare_call",
        "bare.py: bare_call",
    ]


def test_gate_names_a_file_without_an_opening_block(tmp_path: Path) -> None:
    """A header that opens straight into code has no overview."""
    header = tmp_path / "nameless.h"
    header.write_text(
        "#pragma once\n/** Documented. */\nint call();\n", encoding="utf-8"
    )
    files = [api_page.collect_header(header, tmp_path, "C API", True)]
    assert api_page.undocumented(files) == ["nameless.h: opening block"]


def test_the_real_tree_is_fully_documented(
    all_files: list[SourceFile],
) -> None:
    """Every file and declaration under the repository root is documented."""
    files = all_files
    assert [source.path for source in files] == [
        "include/undead/undead.h",
        "include/undead/DialSearch.h",
        "include/undead/DistanceMap.h",
        "include/undead/GridGraph.h",
        "bindings/python/undead/__init__.py",
        "bindings/js/undead.mjs",
    ]
    assert api_page.undocumented(files) == []


def test_check_exits_one_when_something_is_undocumented(
    tmp_path: Path,
) -> None:
    """--check fails on a tree holding one undocumented C++ method."""
    shutil.copytree(ROOT / "include", tmp_path / "include")
    shutil.copytree(ROOT / "bindings", tmp_path / "bindings")
    grid = tmp_path / "include" / "undead" / "GridGraph.h"
    text = grid.read_text(encoding="utf-8")
    marker = (
        "\t\t/**\n\t\t * @brief The number of cells, width * height."
        "\n\t\t */\n"
    )
    assert marker in text
    grid.write_text(text.replace(marker, ""), encoding="utf-8")
    assert api_page.main(["--check", "--root", str(tmp_path)]) == 1
    assert api_page.main(["--check", "--root", str(ROOT)]) == 0


# The page.


def page_of(files: list[SourceFile]) -> str:
    """Render files with the real style and script.

    Example:
        page_of(api_page.collect_all(ROOT)).startswith("<!doctype html>")

    """
    style = (ROOT / "docs" / "api_page.css").read_text(encoding="utf-8")
    script = (ROOT / "docs" / "api_page.js").read_text(encoding="utf-8")
    return api_page.render_page(files, style, script)


def test_page_has_an_anchor_and_a_link_for_every_entry(
    all_files: list[SourceFile],
) -> None:
    """Each entry is deep-linkable and listed in the sidebar."""
    files = all_files
    page = page_of(files)
    checked = 0
    for source in files:
        for entry in source.entries:
            anchor = api_page.anchor_of(source, entry)
            assert f'id="{anchor}"' in page, entry.name
            assert f'href="#{anchor}"' in page, entry.name
            checked += 1
    # A loop over no entries would pass without checking anything.
    assert checked > 0


def test_page_escapes_code(all_files: list[SourceFile]) -> None:
    """A template's angle brackets reach the page escaped."""
    page = page_of(all_files)
    assert "template &lt;SearchGraph Graph&gt;" in page
    assert "template <SearchGraph Graph>" not in page


def test_page_is_self_contained_and_deterministic(
    all_files: list[SourceFile],
) -> None:
    """No external resource is loaded, and two renders are identical."""
    files = all_files
    page = page_of(files)
    assert page.startswith("<!doctype html>")
    assert "<script src" not in page
    assert '<link rel="stylesheet"' not in page
    assert page == page_of(api_page.collect_all(ROOT))


def test_page_script_is_valid_javascript() -> None:
    """The script the page inlines passes node --check."""
    node = shutil.which("node")
    assert node is not None, "node is required to check the page's script"
    result = subprocess.run(
        [node, "--check", str(ROOT / "docs" / "api_page.js")],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert result.returncode == 0, result.stderr
