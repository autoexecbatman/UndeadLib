"""api_page_js: the JSDoc parser and what the JavaScript binding yields.

Expected entries are named from bindings/js/undead.mjs as written, so an
export the reader loses, or a private one it lists, fails a test by name.
"""

from pathlib import Path

import pytest

import api_page
import api_page_js
from api_model import DocPart, Entry, Field, SourceFile

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "bindings" / "js" / "undead.mjs"


@pytest.fixture(scope="module")
def js_file() -> SourceFile:
    """Return the JavaScript binding, collected.

    Example:
        js_file.path  # -> 'bindings/js/undead.mjs'

    """
    return api_page_js.collect_js_module(MODULE, ROOT)


def entry_named(source: SourceFile, name: str) -> Entry:
    """Return the one entry with that name, failing unless there is one.

    Example:
        entry_named(js_file, "UndeadLibrary.load").kind  # -> 'static method'

    """
    matches = [entry for entry in source.entries if entry.name == name]
    assert len(matches) == 1, [entry.name for entry in source.entries]
    return matches[0]


def collect_text(tmp_path: Path, text: str) -> SourceFile:
    r"""Write text as a module under tmp_path and collect it.

    Example:
        collect_text(tmp_path, "/** @file x */\n").path  # -> 'bare.mjs'

    """
    module = tmp_path / "bare.mjs"
    module.write_text(text, encoding="utf-8")
    return api_page_js.collect_js_module(module, tmp_path)


# The JSDoc parser.


def test_jsdoc_splits_prose_example_and_tags() -> None:
    """Prose, @example, @param, @returns and @throws become parts in order."""
    raw = "\n".join(
        [
            "/**",
            " * Distance to every cell.",
            " * Walls stay null.",
            " *",
            " * @example",
            " *   const map = library.dijkstraMap(1, 1, costs, 4, [0]);",
            " *",
            " *   map[0];  // -> 0",
            " *",
            " * @param {number} width - Cells per row.",
            " * @param {Uint8Array} stepCosts - Costs,",
            " *   one per cell.",
            " * @returns {(number | null)[]} One distance per cell.",
            " * @throws {RangeError} If a size would wrap.",
            " */",
        ]
    )
    assert api_page_js.parse_jsdoc_comment(raw).parts == [
        DocPart("text", "", "Distance to every cell. Walls stay null.", []),
        DocPart(
            "code",
            "",
            "const map = library.dijkstraMap(1, 1, costs, 4, [0]);\n\n"
            "map[0];  // -> 0",
            [],
        ),
        DocPart(
            "fields",
            "Parameters",
            "",
            [
                Field("width: number", "Cells per row."),
                Field("stepCosts: Uint8Array", "Costs, one per cell."),
            ],
        ),
        DocPart(
            "fields",
            "Returns",
            "",
            [Field("(number | null)[]", "One distance per cell.")],
        ),
        DocPart(
            "fields",
            "Throws",
            "",
            [Field("RangeError", "If a size would wrap.")],
        ),
    ]


def test_jsdoc_example_keeps_relative_indentation() -> None:
    """An example is dedented as a block, not line by line."""
    raw = "/**\n * @example\n *   if (ready) {\n *     go();\n *   }\n */"
    assert api_page_js.parse_jsdoc_comment(raw).parts == [
        DocPart("code", "", "if (ready) {\n  go();\n}", []),
    ]


def test_jsdoc_file_tag_is_dropped_and_what_follows_is_prose() -> None:
    """@file names the file, which the page already shows."""
    raw = "/**\n * @file undead.mjs\n * The binding.\n */"
    assert api_page_js.parse_jsdoc_comment(raw).parts == [
        DocPart("text", "", "The binding.", []),
    ]


def test_jsdoc_param_without_a_type_and_with_nested_braces() -> None:
    """A missing type leaves the bare name; braces nest inside a type."""
    raw = (
        "/**\n * @param plain - No type.\n"
        " * @param {{ size: number }} options - An object.\n */"
    )
    assert api_page_js.parse_jsdoc_comment(raw).parts == [
        DocPart(
            "fields",
            "Parameters",
            "",
            [
                Field("plain", "No type."),
                Field("options: { size: number }", "An object."),
            ],
        ),
    ]


def test_jsdoc_unknown_tag_is_refused() -> None:
    """A tag the page cannot render fails loudly instead of becoming prose."""
    with pytest.raises(ValueError, match="@deprecated"):
        api_page_js.parse_jsdoc_comment("/** @deprecated Use another. */")


# What the binding yields.


def test_js_binding_lists_exports_and_public_members_only(
    js_file: SourceFile,
) -> None:
    """Private members, helpers and unexported constants are absent."""
    assert js_file.section == "JavaScript binding"
    assert js_file.path == "bindings/js/undead.mjs"
    assert [(entry.name, entry.kind) for entry in js_file.entries] == [
        ("Connectivity", "const"),
        ("UndeadError", "class"),
        ("UndeadError.constructor", "constructor"),
        ("UndeadLibrary", "class"),
        ("UndeadLibrary.constructor", "constructor"),
        ("UndeadLibrary.load", "static method"),
        ("UndeadLibrary.dijkstraMap", "method"),
    ]


def test_js_signatures_stop_at_the_body(js_file: SourceFile) -> None:
    """A const keeps its value; a class or method stops before its brace."""
    signatures = {entry.name: entry.signature for entry in js_file.entries}
    assert signatures["Connectivity"] == (
        "export const Connectivity = "
        "Object.freeze({ FOUR_WAY: 4, EIGHT_WAY: 8 })"
    )
    assert (
        signatures["UndeadError"] == "export class UndeadError extends Error"
    )
    assert signatures["UndeadLibrary.load"] == "static async load(moduleUrl)"
    assert signatures["UndeadLibrary.dijkstraMap"] == (
        "dijkstraMap(width, height, stepCosts, connectivity, sources)"
    )


def test_js_entries_carry_their_comments(js_file: SourceFile) -> None:
    """The comment above dijkstraMap is attached to it, tags parsed."""
    doc = entry_named(js_file, "UndeadLibrary.dijkstraMap").doc
    assert doc is not None
    titles = [part.title for part in doc.parts if part.kind == "fields"]
    assert titles == ["Parameters", "Returns", "Throws"]
    parameters = next(part for part in doc.parts if part.title == "Parameters")
    assert [item.name for item in parameters.fields] == [
        "width: number",
        "height: number",
        "stepCosts: Uint8Array",
        "connectivity: number",
        "sources: number[]",
    ]
    code = [part.text for part in doc.parts if part.kind == "code"]
    assert len(code) == 1 and code[0].startswith("const room = ")


def test_js_overview_is_the_file_block(js_file: SourceFile) -> None:
    """The @file block is the overview, not the first export's comment."""
    assert js_file.overview is not None
    assert js_file.overview.parts[0].text.startswith(
        "JavaScript binding of UndeadLib's C API"
    )


def test_js_multi_line_signature_is_joined(tmp_path: Path) -> None:
    """Parameters on their own lines become one line, trailing comma gone."""
    source = collect_text(
        tmp_path,
        "/** @file bare.mjs */\n\n/** Spread. */\n"
        "export function spread(\n\talpha,\n\tbeta,\n) {\n\treturn 0;\n}\n",
    )
    assert source.entries[0].signature == "export function spread(alpha, beta)"


def test_js_braces_in_strings_and_comments_do_not_count(
    tmp_path: Path,
) -> None:
    """An unbalanced brace in a string or comment does not end a class."""
    source = collect_text(
        tmp_path,
        "/** @file bare.mjs */\n\n/** Holder. */\nexport class Holder {\n"
        "\t/** Open. */\n\topen() {\n\t\treturn \"{\" + `}${1}` + '{';"
        " // }\n\t}\n\n\t/** Close. */\n\tclose() {\n\t\t/* { */\n\t}\n}\n",
    )
    assert [entry.name for entry in source.entries] == [
        "Holder",
        "Holder.open",
        "Holder.close",
    ]


def test_js_escaped_quote_does_not_end_a_string(tmp_path: Path) -> None:
    """A brace after an escaped quote is still inside the string."""
    source = collect_text(
        tmp_path,
        "/** @file bare.mjs */\n\n/** Quote. */\n"
        "export const quote = 'it\\'s {';\n\n/** After. */\n"
        "export function after() {}\n",
    )
    assert [entry.name for entry in source.entries] == ["quote", "after"]


def test_js_unknown_export_forms_are_refused(tmp_path: Path) -> None:
    """An export default or export { } is refused, naming its line."""
    with pytest.raises(ValueError, match="bare.mjs:3"):
        collect_text(tmp_path, "/** @file bare.mjs */\n\nexport default 1;\n")
    with pytest.raises(ValueError, match="bare.mjs:3"):
        collect_text(tmp_path, "/** @file bare.mjs */\n\nexport { a };\n")


def test_js_gate_names_an_undocumented_export(tmp_path: Path) -> None:
    """An uncommented export is named; the file's own block is present."""
    source = collect_text(
        tmp_path, "/** @file bare.mjs */\n\nexport function bare() {}\n"
    )
    assert api_page.undocumented([source]) == ["bare.mjs: bare"]


def test_js_gate_names_a_module_without_a_file_block(tmp_path: Path) -> None:
    """A module whose first comment documents an export has no overview."""
    source = collect_text(
        tmp_path, "/** Documented. */\nexport const a = 1;\n"
    )
    assert api_page.undocumented([source]) == ["bare.mjs: opening block"]
