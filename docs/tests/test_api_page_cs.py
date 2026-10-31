"""api_page_cs: the XML comment parser and what the C# binding yields.

Expected entries are named from bindings/csharp/Undead/*.cs as written, so a
public member the reader loses, or a private one it lists, fails by name.
"""

from pathlib import Path

import pytest

import api_page
import api_page_cs
from api_model import DocPart, Entry, Field, SourceFile

ROOT = Path(__file__).resolve().parents[2]
BINDING = ROOT / "bindings" / "csharp" / "Undead"


@pytest.fixture(scope="module")
def library_file() -> SourceFile:
    """Return UndeadLibrary.cs, collected.

    Example:
        library_file.entries[0].name  # -> 'UndeadLibrary'

    """
    return api_page_cs.collect_cs_file(BINDING / "UndeadLibrary.cs", ROOT)


def entry_named(source: SourceFile, name: str) -> Entry:
    """Return the one entry with that name, failing unless there is one.

    Example:
        entry_named(library_file, "UndeadLibrary.Dispose").kind  # -> 'method'

    """
    matches = [entry for entry in source.entries if entry.name == name]
    assert len(matches) == 1, [entry.name for entry in source.entries]
    return matches[0]


def collect_text(tmp_path: Path, text: str) -> SourceFile:
    r"""Write text as Bare.cs under tmp_path and collect it.

    Example:
        collect_text(tmp_path, "// Bare.\nnamespace A;\n").path  # -> 'Bare.cs'

    """
    source = tmp_path / "Bare.cs"
    source.write_text(text, encoding="utf-8")
    return api_page_cs.collect_cs_file(source, tmp_path)


# The XML comment parser.


def test_xml_doc_splits_summary_example_and_tags() -> None:
    """Summary, example, param, returns and exception become parts."""
    lines = [
        "<summary>Distance to every cell.",
        "Walls stay null.</summary>",
        "<example>",
        "<code>",
        "if (ready)",
        "{",
        "    Go();",
        "}",
        "</code>",
        "</example>",
        '<param name="width">Cells per row.</param>',
        "<returns>One distance per cell.</returns>",
        '<exception cref="OverflowException">If it overflows.</exception>',
    ]
    assert api_page_cs.parse_xml_doc(lines).parts == [
        DocPart("text", "", "Distance to every cell. Walls stay null.", []),
        DocPart("code", "", "if (ready)\n{\n    Go();\n}", []),
        DocPart(
            "fields", "Parameters", "", [Field("width", "Cells per row.")]
        ),
        DocPart(
            "fields", "Returns", "", [Field("", "One distance per cell.")]
        ),
        DocPart(
            "fields",
            "Throws",
            "",
            [Field("OverflowException", "If it overflows.")],
        ),
    ]


def test_xml_doc_inline_tags_become_their_text() -> None:
    """The c, see and paramref tags read as the names they hold."""
    lines = [
        '<summary>Pass <c>null</c> to <see cref="Undead.Load"/>,',
        'not <paramref name="width"/>.</summary>',
    ]
    assert api_page_cs.parse_xml_doc(lines).parts == [
        DocPart("text", "", "Pass null to Undead.Load, not width.", []),
    ]


def test_xml_doc_example_prose_and_para_are_paragraphs() -> None:
    """Text around an example's code, and each para, is its own paragraph."""
    lines = [
        "<remarks><para>First.</para><para>Second.</para></remarks>",
        "<example>Call it:<code>Run();</code></example>",
    ]
    assert api_page_cs.parse_xml_doc(lines).parts == [
        DocPart("text", "", "First.", []),
        DocPart("text", "", "Second.", []),
        DocPart("text", "", "Call it:", []),
        DocPart("code", "", "Run();", []),
    ]


def test_xml_doc_unknown_tag_is_refused() -> None:
    """A tag the page cannot render fails loudly instead of vanishing."""
    with pytest.raises(ValueError, match="inheritdoc"):
        api_page_cs.parse_xml_doc(["<inheritdoc/>"])


# What the binding yields.


def test_library_lists_public_members_only(library_file: SourceFile) -> None:
    """Internal and private members and the fields are absent."""
    assert library_file.section == "C# binding"
    assert library_file.path == "bindings/csharp/Undead/UndeadLibrary.cs"
    assert [(entry.name, entry.kind) for entry in library_file.entries] == [
        ("UndeadLibrary", "class"),
        ("UndeadLibrary.UndeadLibrary", "constructor"),
        ("UndeadLibrary.DijkstraMap", "method"),
        ("UndeadLibrary.Dispose", "method"),
    ]


def test_signatures_stop_at_the_body(library_file: SourceFile) -> None:
    """A multi-line parameter list is joined; the base list stays."""
    signatures = {
        entry.name: entry.signature for entry in library_file.entries
    }
    assert signatures["UndeadLibrary"] == (
        "public sealed unsafe class UndeadLibrary : IDisposable"
    )
    assert signatures["UndeadLibrary.UndeadLibrary"] == (
        "public UndeadLibrary(string dllPath)"
    )
    assert signatures["UndeadLibrary.DijkstraMap"] == (
        "public uint?[] DijkstraMap(\n"
        "    int width,\n"
        "    int height,\n"
        "    ReadOnlySpan<byte> stepCosts,\n"
        "    Connectivity connectivity,\n"
        "    ReadOnlySpan<int> sources)"
    )


def test_long_signature_splits_only_top_level_commas(tmp_path: Path) -> None:
    """A comma inside a generic argument list does not start a parameter."""
    source = collect_text(
        tmp_path,
        "// Bare.\nnamespace A;\n/// <summary>Box.</summary>\n"
        "public class Box\n{\n\t/// <summary>Fill.</summary>\n"
        "\tpublic void Fill(Dictionary<int, string> namesByIndex, "
        "Func<int, int> transform) { }\n}\n",
    )
    assert source.entries[1].signature == (
        "public void Fill(\n"
        "    Dictionary<int, string> namesByIndex,\n"
        "    Func<int, int> transform)"
    )


def test_members_carry_their_comments(library_file: SourceFile) -> None:
    """DijkstraMap's XML comment is attached to it, tags parsed."""
    doc = entry_named(library_file, "UndeadLibrary.DijkstraMap").doc
    assert doc is not None
    titles = [part.title for part in doc.parts if part.kind == "fields"]
    assert titles == ["Parameters", "Returns", "Throws"]
    code = [part.text for part in doc.parts if part.kind == "code"]
    assert len(code) == 1 and code[0].startswith("byte[] room = ")


def test_enum_values_are_its_members() -> None:
    """An enum's values are listed inside it, each with its comment."""
    source = api_page_cs.collect_cs_file(BINDING / "Connectivity.cs", ROOT)
    assert [(entry.name, entry.kind) for entry in source.entries] == [
        ("Connectivity", "enum"),
    ]
    assert source.entries[0].members == [
        Field("FourWay = 4", "The four cells sharing an edge."),
        Field("EightWay = 8", "Those four and the four diagonals."),
    ]


def test_overview_is_the_opening_comment(library_file: SourceFile) -> None:
    """The // block at the top of the file is the overview."""
    assert library_file.overview is not None
    assert library_file.overview.parts[0].text.startswith(
        "UndeadLibrary: the C API in undead_c.dll"
    )


def test_properties_fields_and_expression_bodies(tmp_path: Path) -> None:
    """Each member form is named and stops before its body or value."""
    source = collect_text(
        tmp_path,
        "// Bare.\n\nnamespace A;\n\n/// <summary>Box.</summary>\n"
        "public class Box\n{\n"
        "\t/// <summary>Count.</summary>\n\tpublic int Count => 3;\n\n"
        "\t/// <summary>Name.</summary>\n\tpublic string Name { get; }\n\n"
        "\t/// <summary>Limit.</summary>\n\tpublic const int Limit = 5;\n\n"
        "\t/// <summary>Twice.</summary>\n"
        "\tpublic int Twice(int value) => value * 2;\n"
        '\n\tprivate string hidden = "}";\n}\n',
    )
    assert [
        (entry.name, entry.kind, entry.signature) for entry in source.entries
    ] == [
        ("Box", "class", "public class Box"),
        ("Box.Count", "property", "public int Count"),
        ("Box.Name", "property", "public string Name"),
        ("Box.Limit", "field", "public const int Limit = 5"),
        ("Box.Twice", "method", "public int Twice(int value)"),
    ]


def test_block_namespace_and_nested_type_are_refused(tmp_path: Path) -> None:
    """Forms the reader does not place are refused, naming the line."""
    with pytest.raises(ValueError, match="Bare.cs:3"):
        collect_text(tmp_path, "// Bare.\n\nnamespace A\n{\n}\n")
    with pytest.raises(ValueError, match="Bare.cs:7"):
        collect_text(
            tmp_path,
            "// Bare.\n\nnamespace A;\n\npublic class Box\n{\n"
            "\tpublic enum Inner { One }\n}\n",
        )


def test_xml_doc_indented_example_is_dedented() -> None:
    """Code indented inside the comment loses the shared indentation."""
    lines = [
        "<example><code>",
        "    Run();",
        "      Stop();",
        "</code></example>",
    ]
    assert api_page_cs.parse_xml_doc(lines).parts == [
        DocPart("code", "", "Run();\n  Stop();", []),
    ]


def test_file_opening_with_an_xml_comment(tmp_path: Path) -> None:
    """A /// on line one documents the type below it and is no overview."""
    source = collect_text(
        tmp_path, "/// <summary>Box.</summary>\npublic class Box\n{\n}\n"
    )
    assert source.overview is None
    assert source.entries[0].doc is not None


def test_xml_doc_unknown_inline_tag_is_refused() -> None:
    """An unknown tag inside a summary is refused, not dropped."""
    with pytest.raises(ValueError, match="<b>"):
        api_page_cs.parse_xml_doc(["<summary>See <b>this</b>.</summary>"])


def test_internal_type_after_a_public_one_is_not_listed(
    tmp_path: Path,
) -> None:
    """Members of an internal type are neither listed nor given to Box."""
    source = collect_text(
        tmp_path,
        "// Bare.\n\nnamespace A;\n\n/// <summary>Box.</summary>\n"
        "public class Box\n{\n}\n\ninternal class Hidden\n{\n"
        "\t/// <summary>Run.</summary>\n\tpublic void Run()\n\t{\n\t}\n}\n",
    )
    assert [entry.name for entry in source.entries] == ["Box"]


def test_public_line_that_is_not_a_type_is_refused(tmp_path: Path) -> None:
    """A public top-level delegate is a form the reader does not list."""
    with pytest.raises(ValueError, match="Bare.cs:3"):
        collect_text(
            tmp_path, "// Bare.\nnamespace A;\npublic delegate void D();\n"
        )


def test_one_line_enum_is_refused(tmp_path: Path) -> None:
    """An enum whose values share its line would be listed with none."""
    with pytest.raises(ValueError, match="Bare.cs:3"):
        collect_text(
            tmp_path, "// Bare.\nnamespace A;\npublic enum E { One }\n"
        )


def test_gate_names_an_undocumented_member(tmp_path: Path) -> None:
    """A public member with no XML comment is named; the header is there."""
    source = collect_text(
        tmp_path,
        "// Bare.\n\nnamespace A;\n\n/// <summary>Box.</summary>\n"
        "public class Box\n{\n\tpublic void Open()\n\t{\n\t}\n}\n",
    )
    assert api_page.undocumented([source]) == ["Bare.cs: Box.Open"]


def test_gate_names_a_file_without_an_opening_comment(tmp_path: Path) -> None:
    """A file that starts with code has no overview."""
    source = collect_text(
        tmp_path,
        "namespace A;\n\n/// <summary>Box.</summary>\n"
        "public class Box\n{\n}\n",
    )
    assert api_page.undocumented([source]) == ["Bare.cs: opening block"]
