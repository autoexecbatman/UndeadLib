r"""The API page's data model, shared by every reader and by the renderer.

A reader turns one source file into a SourceFile: its overview and its
listed declarations (Entry), each documented by a DocBlock of ordered parts.
api_page.py reads C, C++ and Python; api_page_js.py reads JavaScript.

Usage:

    from api_model import DocBlock, DocPart, Entry, Field, SourceFile
    from api_model import add_field, comment_lines

    parts: list[DocPart] = []
    add_field(parts, "Parameters", Field("width", "Cells per row."))
    block = DocBlock(parts)
    entry = Entry("dijkstra_map", "function", "def dijkstra_map(...)",
                  12, block, [])          # name, kind, signature, line, doc
    source = SourceFile("C API", "include/undead/undead.h", None, [entry])
    comment_lines("/**\n * A wall.\n */")  # -> ['A wall.']
"""

from dataclasses import dataclass


@dataclass
class Field:
    """One named item in a doc block: a parameter, an exception, a value."""

    name: str
    text: str


@dataclass
class DocPart:
    """One section of a doc block, rendered in order.

    kind is "text" (prose), "code" (an example) or "fields" (a titled list).
    """

    kind: str
    title: str
    text: str
    fields: list[Field]


@dataclass
class DocBlock:
    """A parsed comment or docstring, as the parts it is rendered from."""

    parts: list[DocPart]


@dataclass
class Entry:
    """One listed declaration and what documents it."""

    name: str
    kind: str
    signature: str
    line: int
    doc: DocBlock | None
    members: list[Field]


@dataclass
class SourceFile:
    """One header or module: its overview and its listed declarations."""

    section: str
    path: str
    overview: DocBlock | None
    entries: list[Entry]


def add_field(parts: list[DocPart], title: str, item: Field) -> None:
    """Append item to the fields part titled title, starting one if needed.

    Example:
        parts: list[DocPart] = []
        add_field(parts, "Parameters", Field("width", "Cells per row."))
        add_field(parts, "Parameters", Field("height", "Rows."))
        len(parts)  # -> 1, both fields under one heading

    """
    if parts and parts[-1].kind == "fields" and parts[-1].title == title:
        parts[-1].fields.append(item)
        return
    parts.append(DocPart("fields", title, "", [item]))


def comment_lines(raw: str) -> list[str]:
    r"""Return a /** */ comment's lines without the delimiters and stars.

    Example:
        comment_lines("/**\n * @brief A.\n *   code\n */")
        # -> ['@brief A.', '  code']

    """
    body = raw.strip().removeprefix("/**").removesuffix("*/")
    lines = []
    for line in body.splitlines():
        stripped = line.lstrip()
        # One star and one space are the comment's frame; the rest is content.
        if stripped.startswith("*"):
            content = stripped[1:]
            content = content.removeprefix(" ")
        else:
            content = stripped
        lines.append(content.rstrip())
    # Blank first and last lines are what the delimiters sat on.
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return lines
