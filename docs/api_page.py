"""Render UndeadLib's public API into one self-contained HTML page.

Headers are read with libclang and the Python binding with ast; nothing is
imported or executed. The page is also a coverage gate: a listed declaration
with no comment, or a file with no opening block, fails the run.

Usage, from the repository root:

    python docs/api_page.py --root . --out build/docs/api.html  # write it
    python docs/api_page.py --root . --check                    # report only

From Python:

    files = collect_all(Path("D:/repo/UndeadLib"))
    [source.path for source in files][0]  # -> 'include/undead/undead.h'
    undocumented(files)                   # -> [] when everything is
    page = render_page(files, style, script)  # the HTML, as a string

Exit codes: 0 everything listed is documented, 1 something is not.
"""

import argparse
import ast
import html
import inspect
import os
import re
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path

import clang.cindex as cindex

# The page's stylesheet and script, inlined so the page stands alone.
STYLE = Path(__file__).parent / "api_page.css"
SCRIPT = Path(__file__).parent / "api_page.js"

C_API_SECTION = "C API"
CPP_SECTION = "C++ core"
PYTHON_SECTION = "Python binding"

# Decorates declarations for export; a caller never writes it.
EXPORT_MACRO = "UNDEAD_API"

# Google docstring headings and the title each renders under.
_GOOGLE_SECTIONS = {
    "Example:": "Example",
    "Examples:": "Example",
    "Args:": "Parameters",
    "Returns:": "Returns",
    "Raises:": "Raises",
}

_KIND_LABELS = {
    cindex.CursorKind.CLASS_DECL: "class",
    cindex.CursorKind.STRUCT_DECL: "struct",
    cindex.CursorKind.ENUM_DECL: "enum",
    cindex.CursorKind.CONCEPT_DECL: "concept",
    cindex.CursorKind.FUNCTION_DECL: "function",
    cindex.CursorKind.FUNCTION_TEMPLATE: "function template",
    cindex.CursorKind.CONSTRUCTOR: "constructor",
    cindex.CursorKind.DESTRUCTOR: "destructor",
    cindex.CursorKind.CXX_METHOD: "method",
    cindex.CursorKind.FIELD_DECL: "field",
}

_FUNCTION_KINDS = {
    cindex.CursorKind.FUNCTION_DECL,
    cindex.CursorKind.FUNCTION_TEMPLATE,
    cindex.CursorKind.CONSTRUCTOR,
    cindex.CursorKind.DESTRUCTOR,
    cindex.CursorKind.CXX_METHOD,
}

# Tokens after a parameter list that are still part of the interface.
_TRAILING_QUALIFIERS = {"const", "noexcept", "override", "final", "&", "&&"}


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


def _add_field(parts: list[DocPart], title: str, item: Field) -> None:
    """Append item to the fields part titled title, starting one if needed.

    Example:
        parts: list[DocPart] = []
        _add_field(parts, "Parameters", Field("width", "Cells per row."))
        _add_field(parts, "Parameters", Field("height", "Rows."))
        len(parts)  # -> 1, both fields under one heading

    """
    if parts and parts[-1].kind == "fields" and parts[-1].title == title:
        parts[-1].fields.append(item)
        return
    parts.append(DocPart("fields", title, "", [item]))


def _comment_lines(raw: str) -> list[str]:
    r"""Return a /** */ comment's lines without the delimiters and stars.

    Example:
        _comment_lines("/**\n * @brief A.\n *   code\n */")
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


def parse_doxygen_comment(raw: str) -> DocBlock:
    """Parse a /** */ comment's prose, @code blocks and tags into parts.

    @brief joins the prose; @param, @returns and @throws become titled
    fields; @file is dropped, since the page already names the file. A line
    that follows a tag continues it until a blank line.

    Example:
        parse_doxygen_comment("/** @returns The map. */").parts
        # -> [DocPart("fields", "Returns", "", [Field("", "The map.")])]

    """
    parts: list[DocPart] = []
    prose: list[str] = []
    code: list[str] = []
    is_in_code = False
    current: Field | None = None

    # Prose collected so far becomes one paragraph.
    def flush_prose() -> None:
        if prose:
            parts.append(DocPart("text", "", " ".join(prose), []))
            prose.clear()

    for line in _comment_lines(raw):
        stripped = line.strip()
        # Inside @code every line is kept as written until @endcode.
        if is_in_code:
            if stripped == "@endcode":
                example = textwrap.dedent("\n".join(code)).strip("\n")
                parts.append(DocPart("code", "", example, []))
                code.clear()
                is_in_code = False
            else:
                code.append(line)
            continue
        if stripped == "@code":
            flush_prose()
            current = None
            is_in_code = True
            continue
        # A blank line ends a paragraph and any tag it continued.
        if not stripped:
            flush_prose()
            current = None
            continue
        tag, _, rest = stripped.partition(" ")
        rest = rest.strip()
        if tag == "@file":
            continue
        if tag == "@brief":
            prose.append(rest)
            continue
        if tag.startswith("@param"):
            flush_prose()
            name, _, text = rest.partition(" ")
            current = Field(name, text.strip())
            _add_field(parts, "Parameters", current)
            continue
        if tag in ("@returns", "@return"):
            flush_prose()
            current = Field("", rest)
            _add_field(parts, "Returns", current)
            continue
        if tag in ("@throws", "@throw"):
            flush_prose()
            name, _, text = rest.partition(" ")
            current = Field(name, text.strip())
            _add_field(parts, "Throws", current)
            continue
        # An untagged line continues the open tag, or else the paragraph.
        if current is not None:
            current.text = f"{current.text} {stripped}".strip()
        else:
            prose.append(stripped)
    flush_prose()
    return DocBlock(parts)


def _indented_run(lines: list[str], start: int) -> int:
    """Return the index after the run of indented or blank lines at start.

    Example:
        _indented_run(["    a", "", "    b", "c"], 0)  # -> 3

    """
    end = start
    while end < len(lines) and (
        not lines[end].strip() or lines[end].startswith((" ", "\t"))
    ):
        end += 1
    return end


def _section_fields(block: list[str]) -> list[Field]:
    """Split an Args or Raises block into one field per "name: text" entry.

    Example:
        _section_fields(["width: Cells.", "sources: Cell", "    indices."])
        # -> [Field("width", "Cells."), Field("sources", "Cell indices.")]

    """
    fields: list[Field] = []
    for line in block:
        if not line.strip():
            continue
        # An entry starts at the block's own indentation; deeper continues it.
        if not line.startswith((" ", "\t")):
            name, _, text = line.partition(":")
            fields.append(Field(name.strip(), text.strip()))
        elif fields:
            fields[-1].text = f"{fields[-1].text} {line.strip()}".strip()
    return fields


def parse_google_docstring(text: str) -> DocBlock:
    r"""Parse a Google-style docstring into prose, code and field parts.

    Example: becomes code; Args: and Raises: become fields per entry;
    Returns: becomes one field. An indented block outside a section is a
    usage example and becomes code.

    Example:
        parse_google_docstring("Do it.\n\nReturns:\n    Nothing.").parts
        # -> [DocPart("text", "", "Do it.", []),
        #     DocPart("fields", "Returns", "", [Field("", "Nothing.")])]

    """
    lines = inspect.cleandoc(text).splitlines()
    parts: list[DocPart] = []
    prose: list[str] = []

    # Prose collected so far becomes one paragraph.
    def flush_prose() -> None:
        if prose:
            parts.append(DocPart("text", "", " ".join(prose), []))
            prose.clear()

    index = 0
    while index < len(lines):
        line = lines[index]
        # A section heading owns the indented lines under it.
        if line in _GOOGLE_SECTIONS:
            flush_prose()
            end = _indented_run(lines, index + 1)
            block = textwrap.dedent("\n".join(lines[index + 1 : end]))
            title = _GOOGLE_SECTIONS[line]
            if title == "Example":
                parts.append(DocPart("code", "", block.strip("\n"), []))
            elif title == "Returns":
                returned = " ".join(block.split())
                _add_field(parts, "Returns", Field("", returned))
            else:
                for item in _section_fields(block.splitlines()):
                    _add_field(parts, title, item)
            index = end
            continue
        # An indented run outside any section is a usage example.
        if line.startswith((" ", "\t")):
            flush_prose()
            end = _indented_run(lines, index)
            block = textwrap.dedent("\n".join(lines[index:end]))
            parts.append(DocPart("code", "", block.strip("\n"), []))
            index = end
            continue
        if not line.strip():
            flush_prose()
        else:
            prose.append(line.strip())
        index += 1
    flush_prose()
    return DocBlock(parts)


def _opening_comment(text: str) -> str | None:
    r"""Return the /** */ block a file opens with, or None if code comes first.

    Example:
        _opening_comment("/** The C API. */\n#pragma once")
        # -> '/** The C API. */'
        _opening_comment("#pragma once\n/** Later. */")  # -> None

    """
    stripped = text.lstrip()
    if not stripped.startswith("/**"):
        return None
    end = stripped.find("*/")
    return stripped[: end + 2] if end != -1 else None


def _comment_above(lines: list[str], line_number: int) -> str | None:
    """Return the /** */ block ending on the line just above line_number.

    line_number is 1-based, as libclang reports it.

    Example:
        _comment_above(["/** Unreached. */", "#define X 1"], 2)
        # -> '/** Unreached. */'

    """
    end = line_number - 2
    if end < 0 or not lines[end].rstrip().endswith("*/"):
        return None
    start = end
    while start >= 0 and "/**" not in lines[start]:
        start -= 1
    if start < 0:
        return None
    return "\n".join(lines[start : end + 1])


def _is_in_file(cursor: cindex.Cursor, header_key: str) -> bool:
    r"""Return whether the cursor was declared in the header being read.

    Example:
        _is_in_file(cursor, os.path.normcase("d:\\repo\\a.h"))
        # -> True for a declaration in a.h, False for one from <vector>

    """
    location = cursor.location.file
    if location is None:
        return False
    return os.path.normcase(str(Path(location.name).resolve())) == header_key


def _source_text(source: bytes, start: int, end: int) -> str:
    """Return the source between two byte offsets as text.

    Example:
        _source_text(b"int call();", 0, 10)  # -> 'int call()'

    """
    return source[start:end].decode("utf-8")


def _dedented(text: str, column: int) -> str:
    r"""Remove the first line's indentation from every following line.

    column is the 1-based column the first line starts at, so continuation
    lines keep only the indentation they have beyond it.

    Example:
        _dedented("call(\n\t\t\targument)", 3)  # -> 'call(\n    argument)'

    """
    lines = text.split("\n")
    margin = column - 1
    kept = [lines[0]]
    for line in lines[1:]:
        indent = len(line) - len(line.lstrip(" \t"))
        kept.append(line[min(indent, margin) :])
    return "\n".join(line.expandtabs(4).rstrip() for line in kept)


def _signature_end(cursor: cindex.Cursor, start: int) -> int:
    """Return the byte offset where a declaration's interface ends.

    A function ends after its parameter list and any trailing qualifiers, so
    an initializer list and a body are left out. A class or enum ends before
    its opening brace. Anything else ends where its extent does. start is
    where the signature begins; tokens before it are the definition of a
    macro the declaration starts with, which libclang lists first.

    Example:
        _signature_end(node_count_cursor, start)
        # -> the offset just after "noexcept" in "size_t node_count() const
        #    noexcept { ... }"

    """
    tokens = [
        token
        for token in cursor.get_tokens()
        if int(token.extent.start.offset) >= start
    ]
    if cursor.kind in _FUNCTION_KINDS:
        depth = 0
        has_parameters = False
        end = int(cursor.extent.end.offset)
        for position, token in enumerate(tokens):
            spelling = token.spelling
            # The parameter list is the first parenthesised group.
            if not has_parameters:
                if spelling == "(":
                    depth += 1
                elif spelling == ")":
                    depth -= 1
                    if depth == 0:
                        has_parameters = True
                        end = int(token.extent.end.offset)
                continue
            # After it, qualifiers and "= default" are still interface.
            if spelling in _TRAILING_QUALIFIERS:
                end = int(token.extent.end.offset)
                continue
            following = (
                tokens[position + 1].spelling
                if position + 1 < len(tokens)
                else ""
            )
            if spelling == "=" and following in ("default", "delete", "0"):
                end = int(tokens[position + 1].extent.end.offset)
            break
        return end
    if cursor.kind in (
        cindex.CursorKind.CLASS_DECL,
        cindex.CursorKind.STRUCT_DECL,
        cindex.CursorKind.ENUM_DECL,
    ):
        for token in tokens:
            if token.spelling == "{":
                return int(token.extent.start.offset)
    return int(cursor.extent.end.offset)


def _signature_start(cursor: cindex.Cursor, source: bytes) -> int:
    """Return the byte offset where a declaration's interface begins.

    clang's extent leaves out leading [[attributes]], which are interface,
    so a start preceded on its line only by attributes moves back over
    them. An extent that starts inside a macro expansion lies outside the
    declaration's text, so the declaration's own line start is used.

    Example:
        _signature_start(node_count_cursor, source)
        # -> the offset of "[[nodiscard]]", not of "size_t"

    """
    start = int(cursor.extent.start.offset)
    location = int(cursor.location.offset)
    # An extent from a macro expansion does not precede the name in the file.
    if start > location or cursor.extent.start.file is None:
        start = location
    line_start = source.rfind(b"\n", 0, start) + 1
    before = source[line_start:start].decode("utf-8")
    if not before.strip() or re.fullmatch(r"\s*(\[\[[^\]]*\]\]\s*)+", before):
        return line_start + len(before) - len(before.lstrip())
    return start


def _signature(cursor: cindex.Cursor, source: bytes) -> str:
    """Return a declaration's interface as written, dedented, body removed.

    Example:
        _signature(node_count_cursor, source)
        # -> '[[nodiscard]] size_t node_count() const noexcept'

    """
    start = _signature_start(cursor, source)
    line_start = source.rfind(b"\n", 0, start) + 1
    text = _source_text(source, start, _signature_end(cursor, start)).rstrip()
    text = _dedented(text, start - line_start + 1)
    # The export macro decorates the declaration; it is not interface.
    return text.removeprefix(EXPORT_MACRO).lstrip()


def _doc_of(cursor: cindex.Cursor) -> DocBlock | None:
    """Return the parsed /** */ comment libclang attached, or None.

    Example:
        _doc_of(grid_graph_cursor).parts[0].text
        # -> 'A grid of step costs, searchable by DialSearch.'

    """
    raw = cursor.raw_comment
    return parse_doxygen_comment(raw) if raw else None


def _plain_text(block: DocBlock | None) -> str:
    """Return a block's prose as one line, for a short member description.

    Example:
        _plain_text(parse_doxygen_comment("/** A wall. */"))  # -> 'A wall.'

    """
    if block is None:
        return ""
    return " ".join(part.text for part in block.parts if part.kind == "text")


def _enum_members(cursor: cindex.Cursor, source: bytes) -> list[Field]:
    """Return an enum's constants, each with its initializer and comment.

    Example:
        [member.name for member in _enum_members(status_cursor, source)][0]
        # -> 'UNDEAD_OK = 0'

    """
    members = []
    for constant in cursor.get_children():
        if constant.kind != cindex.CursorKind.ENUM_CONSTANT_DECL:
            continue
        written = _source_text(
            source,
            int(constant.extent.start.offset),
            int(constant.extent.end.offset),
        )
        # An explicit value is shown as written; an implicit one is not.
        name = (
            " ".join(written.split()) if "=" in written else constant.spelling
        )
        members.append(Field(name, _plain_text(_doc_of(constant))))
    return members


def _enum_name(cursor: cindex.Cursor, members: list[Field], scope: str) -> str:
    """Return an enum's qualified name, or its constant range when unnamed.

    Example:
        _enum_name(status_cursor, members, "")
        # -> 'enum UNDEAD_OK .. UNDEAD_ERROR_INTERNAL'

    """
    if not cursor.is_anonymous():
        return f"{scope}{cursor.spelling}"
    first = members[0].name.split(" ")[0]
    last = members[-1].name.split(" ")[0]
    return f"enum {first} .. {last}"


def _entry_for(
    cursor: cindex.Cursor, source: bytes, name: str, members: list[Field]
) -> Entry:
    """Build the entry for one declaration.

    Example:
        _entry_for(grid_graph_cursor, source, "undead::GridGraph", []).kind
        # -> 'class'

    """
    return Entry(
        name=name,
        kind=_KIND_LABELS[cursor.kind],
        signature=_signature(cursor, source),
        line=int(cursor.location.line),
        doc=_doc_of(cursor),
        members=members,
    )


def _class_entries(
    cursor: cindex.Cursor, source: bytes, header_key: str, name: str
) -> list[Entry]:
    """Return a class's entry followed by one per public member.

    Example:
        [entry.name for entry in _class_entries(map_cursor, source, key,
                                                "undead::DistanceMap")]
        # -> ['undead::DistanceMap', 'undead::DistanceMap::node_count',
        #     'undead::DistanceMap::distance']

    """
    entries = [_entry_for(cursor, source, name, [])]
    for member in cursor.get_children():
        is_listed_kind = member.kind in _KIND_LABELS
        is_public = member.access_specifier == cindex.AccessSpecifier.PUBLIC
        if is_listed_kind and is_public and _is_in_file(member, header_key):
            entries.append(
                _entry_for(member, source, f"{name}::{member.spelling}", [])
            )
    return entries


def _walk(
    parent: cindex.Cursor,
    source: bytes,
    header_key: str,
    scope: str,
    entries: list[Entry],
) -> None:
    """Append the entries for every listed declaration under parent.

    Namespaces are walked into and qualify the names under them; forward
    declarations and anything from another file are skipped.

    Example:
        entries: list[Entry] = []
        _walk(unit.cursor, source, key, "", entries)
        entries[0].name  # -> 'undead::Connectivity' for GridGraph.h

    """
    for cursor in parent.get_children():
        if not _is_in_file(cursor, header_key):
            continue
        kind = cursor.kind
        if kind == cindex.CursorKind.NAMESPACE:
            inner = f"{scope}{cursor.spelling}::"
            _walk(cursor, source, header_key, inner, entries)
        elif kind == cindex.CursorKind.LINKAGE_SPEC:
            _walk(cursor, source, header_key, scope, entries)
        elif kind in (
            cindex.CursorKind.CLASS_DECL,
            cindex.CursorKind.STRUCT_DECL,
        ):
            if cursor.is_definition():
                name = f"{scope}{cursor.spelling}"
                entries.extend(
                    _class_entries(cursor, source, header_key, name)
                )
        elif kind == cindex.CursorKind.ENUM_DECL:
            if cursor.is_definition():
                members = _enum_members(cursor, source)
                name = _enum_name(cursor, members, scope)
                entries.append(_entry_for(cursor, source, name, members))
        elif kind in _KIND_LABELS:
            name = f"{scope}{cursor.spelling}"
            entries.append(_entry_for(cursor, source, name, []))


def _macro_entries(
    unit: cindex.TranslationUnit, header_key: str, lines: list[str]
) -> list[Entry]:
    """Return an entry per macro the header defines, except the export macro.

    Example:
        [entry.name for entry in _macro_entries(unit, key, lines)]
        # -> ['UNDEAD_UNREACHED'] for undead.h

    """
    entries = []
    for cursor in unit.cursor.get_children():
        if cursor.kind != cindex.CursorKind.MACRO_DEFINITION:
            continue
        if not _is_in_file(cursor, header_key):
            continue
        if cursor.spelling == EXPORT_MACRO:
            continue
        line_number = int(cursor.location.line)
        comment = _comment_above(lines, line_number)
        entries.append(
            Entry(
                name=cursor.spelling,
                kind="macro",
                signature=lines[line_number - 1].strip(),
                line=line_number,
                doc=parse_doxygen_comment(comment) if comment else None,
                members=[],
            )
        )
    return entries


def collect_header(
    header: Path, root: Path, section: str, is_c: bool
) -> SourceFile:
    """Read one header's public declarations and comments with libclang.

    is_c parses it as C11, which is how a C caller sees undead.h; otherwise
    it is parsed as C++20. libclang's own errors about the MSVC standard
    library leave the header's declarations intact, so they are not fatal.

    Example:
        source = collect_header(root / "include/undead/undead.h", root,
                                "C API", True)
        source.path                      # -> 'include/undead/undead.h'
        [entry.name for entry in source.entries][-1]
        # -> 'undead_dijkstra_map'

    """
    language = ["-x", "c", "-std=c11"] if is_c else ["-x", "c++", "-std=c++20"]
    arguments = [
        *language,
        f"-I{root / 'include'}",
        "-D_ALLOW_COMPILER_AND_STL_VERSION_MISMATCH",
        "-w",
    ]
    index = cindex.Index.create()
    # Bodies are never read, and skipping them is most of the parse time,
    # since every standard header's templates have one.
    unit = index.parse(
        str(header),
        args=arguments,
        options=cindex.TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD
        | cindex.TranslationUnit.PARSE_SKIP_FUNCTION_BODIES,
    )
    if unit is None:
        raise RuntimeError(f"libclang could not parse {header}")

    source = header.read_bytes()
    text = source.decode("utf-8")
    header_key = os.path.normcase(str(header.resolve()))
    entries: list[Entry] = []
    _walk(unit.cursor, source, header_key, "", entries)
    entries.extend(_macro_entries(unit, header_key, text.splitlines()))
    # Page order is reading order.
    entries.sort(key=lambda entry: entry.line)

    opening = _opening_comment(text)
    return SourceFile(
        section=section,
        path=header.relative_to(root).as_posix(),
        overview=parse_doxygen_comment(opening) if opening else None,
        entries=entries,
    )


def _python_parameter(argument: ast.arg, default: ast.expr | None) -> str:
    """Return one parameter as written: name, annotation, default.

    Example:
        _python_parameter(width_arg, None)  # -> 'width: int'

    """
    text = argument.arg
    if argument.annotation is not None:
        text = f"{text}: {ast.unparse(argument.annotation)}"
    if default is not None:
        separator = " = " if argument.annotation is not None else "="
        text = f"{text}{separator}{ast.unparse(default)}"
    return text


def _python_parameters(arguments: ast.arguments) -> list[str]:
    """Return a function's parameters in order, with the / and * markers.

    Example:
        _python_parameters(dijkstra_map_node.args)[:2]
        # -> ['self', 'width: int']

    """
    positional = [*arguments.posonlyargs, *arguments.args]
    # Defaults belong to the last positional parameters.
    padding: list[ast.expr | None] = [None] * (
        len(positional) - len(arguments.defaults)
    )
    defaults = [*padding, *arguments.defaults]
    parameters = [
        _python_parameter(argument, default)
        for argument, default in zip(positional, defaults, strict=True)
    ]
    if arguments.posonlyargs:
        parameters.insert(len(arguments.posonlyargs), "/")
    if arguments.vararg is not None:
        parameters.append(f"*{_python_parameter(arguments.vararg, None)}")
    elif arguments.kwonlyargs:
        parameters.append("*")
    parameters.extend(
        _python_parameter(argument, default)
        for argument, default in zip(
            arguments.kwonlyargs, arguments.kw_defaults, strict=True
        )
    )
    if arguments.kwarg is not None:
        parameters.append(f"**{_python_parameter(arguments.kwarg, None)}")
    return parameters


def _python_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Return a function's def line, one parameter per line when it is long.

    A def line longer than 79 characters, the line length the code is held
    to, breaks after the opening parenthesis the way the formatter writes it.

    Example:
        _python_signature(init_node)
        # -> 'def __init__(self, dll_path: Path) -> None'

    """
    returns = f" -> {ast.unparse(node.returns)}" if node.returns else ""
    parameters = _python_parameters(node.args)
    one_line = f"def {node.name}({', '.join(parameters)}){returns}"
    if len(one_line) <= 79:
        return one_line
    listed = "".join(f"    {parameter},\n" for parameter in parameters)
    return f"def {node.name}(\n{listed}){returns}"


def _python_doc(node: ast.AST) -> DocBlock | None:
    """Return a node's parsed docstring, or None when it has none.

    Example:
        _python_doc(connectivity_node).parts[0].text
        # -> 'Which neighbours a cell has; a diagonal costs what ...'

    """
    if not isinstance(
        node,
        ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef,
    ):
        return None
    docstring = ast.get_docstring(node, clean=True)
    return parse_google_docstring(docstring) if docstring else None


def _is_public(name: str) -> bool:
    """Return whether a Python name is part of the public interface.

    Example:
        _is_public("dijkstra_map")      # -> True
        _is_public("_raise_for_status")  # -> False

    """
    return not name.startswith("_")


def _python_class_entries(node: ast.ClassDef) -> list[Entry]:
    """Return a class's entry, with its constants, then its public methods.

    Example:
        [entry.name for entry in _python_class_entries(library_node)]
        # -> ['UndeadLibrary', 'UndeadLibrary.__init__',
        #     'UndeadLibrary.dijkstra_map']

    """
    constants = [
        Field(f"{target.id} = {ast.unparse(statement.value)}", "")
        for statement in node.body
        if isinstance(statement, ast.Assign)
        for target in statement.targets
        if isinstance(target, ast.Name) and _is_public(target.id)
    ]
    bases = ", ".join(ast.unparse(base) for base in node.bases)
    signature = (
        f"class {node.name}({bases})" if bases else f"class {node.name}"
    )
    entries = [
        Entry(
            node.name,
            "class",
            signature,
            node.lineno,
            _python_doc(node),
            constants,
        )
    ]
    for statement in node.body:
        if not isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if not (_is_public(statement.name) or statement.name == "__init__"):
            continue
        entries.append(
            Entry(
                name=f"{node.name}.{statement.name}",
                kind="method",
                signature=_python_signature(statement),
                line=statement.lineno,
                doc=_python_doc(statement),
                members=[],
            )
        )
    return entries


def collect_python_module(module: Path, root: Path) -> SourceFile:
    """Read one module's public classes and functions with ast.

    Example:
        source = collect_python_module(
            root / "bindings/python/undead/__init__.py", root)
        [entry.name for entry in source.entries][0]  # -> 'Connectivity'

    """
    tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
    entries: list[Entry] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and _is_public(node.name):
            entries.extend(_python_class_entries(node))
        elif isinstance(
            node, ast.FunctionDef | ast.AsyncFunctionDef
        ) and _is_public(node.name):
            entries.append(
                Entry(
                    node.name,
                    "function",
                    _python_signature(node),
                    node.lineno,
                    _python_doc(node),
                    [],
                )
            )
    return SourceFile(
        section=PYTHON_SECTION,
        path=module.relative_to(root).as_posix(),
        overview=_python_doc(tree),
        entries=entries,
    )


def undocumented(files: list[SourceFile]) -> list[str]:
    """Name every file with no opening block and every uncommented entry.

    Enum constants and class constants are not required; the declaration
    that holds them documents them.

    Example:
        undocumented(collect_all(root))  # -> [] when everything is
        # otherwise ['include/undead/GridGraph.h: undead::GridGraph::...']

    """
    missing = []
    for source in files:
        if source.overview is None:
            missing.append(f"{source.path}: opening block")
        missing.extend(
            f"{source.path}: {entry.name}"
            for entry in source.entries
            if entry.doc is None
        )
    return missing


def collect_all(root: Path) -> list[SourceFile]:
    """Collect the C API, the C++ core and the Python binding under root.

    Example:
        [source.path for source in collect_all(root)]
        # -> ['include/undead/undead.h', 'include/undead/DialSearch.h', ...,
        #     'bindings/python/undead/__init__.py']

    """
    include = root / "include" / "undead"
    c_header = include / "undead.h"
    files = [collect_header(c_header, root, C_API_SECTION, True)]
    for header in sorted(include.glob("*.h")):
        if header.name != c_header.name:
            files.append(collect_header(header, root, CPP_SECTION, False))
    binding = root / "bindings" / "python" / "undead" / "__init__.py"
    files.append(collect_python_module(binding, root))
    return files


def anchor_of(source: SourceFile, entry: Entry) -> str:
    """Return the HTML id an entry is linked by: its file and its name.

    Example:
        anchor_of(grid_file, node_count_entry)
        # -> 'include-undead-GridGraph-h--undead--GridGraph--node_count'

    """
    return f"{_slug(source.path)}--{_slug(entry.name)}"


def _slug(text: str) -> str:
    """Return text with every character outside [A-Za-z0-9_] made a hyphen.

    Example:
        _slug("include/undead/undead.h")  # -> 'include-undead-undead-h'

    """
    return re.sub(r"[^A-Za-z0-9_]", "-", text)


def _render_doc(block: DocBlock | None) -> str:
    """Render a doc block's parts as HTML, in order.

    Example:
        _render_doc(parse_doxygen_comment("/** A wall. */"))
        # -> '<p>A wall.</p>'

    """
    if block is None:
        return '<p class="missing">Undocumented.</p>'
    rendered = []
    for part in block.parts:
        if part.kind == "text":
            rendered.append(f"<p>{html.escape(part.text)}</p>")
        elif part.kind == "code":
            rendered.append(
                f'<pre class="example"><code>{html.escape(part.text)}'
                "</code></pre>"
            )
        else:
            rendered.append(_render_fields(part.title, part.fields))
    return "".join(rendered)


def _render_fields(title: str, fields: list[Field]) -> str:
    """Render a titled list of fields; an unnamed field is plain text.

    Example:
        _render_fields("Returns", [Field("", "The map.")])
        # -> '<h5>Returns</h5><dl><dd>The map.</dd></dl>'

    """
    items = []
    for item in fields:
        if item.name:
            items.append(f"<dt><code>{html.escape(item.name)}</code></dt>")
        items.append(f"<dd>{html.escape(item.text)}</dd>")
    return f"<h5>{html.escape(title)}</h5><dl>{''.join(items)}</dl>"


def _display_name(entry: Entry) -> str:
    """Return the name the page shows: the namespace prefix is dropped.

    Example:
        _display_name(node_count_entry)  # -> 'GridGraph::node_count'

    """
    return entry.name.removeprefix("undead::")


def _render_sidebar(files: list[SourceFile], sections: list[str]) -> str:
    """Render the sidebar: a filter, then each section's files and entries.

    Example:
        _render_sidebar(files, ["C API"]).startswith('<nav id="sidebar">')
        # -> True

    """
    rendered = [
        '<nav id="sidebar"><input id="filter" type="search" '
        'placeholder="Filter  ( / )" aria-label="Filter declarations">'
    ]
    for section in sections:
        rendered.append(f"<h2>{html.escape(section)}</h2>")
        for source in files:
            if source.section != section:
                continue
            rendered.append(
                f'<h3><a href="#{_slug(source.path)}">'
                f"{html.escape(source.path)}</a></h3><ul>"
            )
            for entry in source.entries:
                name = _display_name(entry)
                rendered.append(
                    f'<li data-name="{html.escape(name.lower())}">'
                    f'<a href="#{anchor_of(source, entry)}" '
                    f'title="{html.escape(name)}">'
                    f"{html.escape(name)}</a></li>"
                )
            rendered.append("</ul>")
    rendered.append("</nav>")
    return "".join(rendered)


def _render_entry(source: SourceFile, entry: Entry) -> str:
    """Render one entry: its name, kind, signature, doc and members.

    Example:
        _render_entry(grid_file, node_count_entry).startswith('<div')
        # -> True

    """
    anchor = anchor_of(source, entry)
    name = _display_name(entry)
    members = _render_fields("Members", entry.members) if entry.members else ""
    return (
        f'<div class="entry" id="{anchor}" '
        f'data-name="{html.escape(name.lower())}">'
        f'<h4><a class="permalink" href="#{anchor}">{html.escape(name)}</a> '
        f'<span class="kind">{html.escape(entry.kind)}</span></h4>'
        f'<pre class="signature"><code>{html.escape(entry.signature)}'
        f"</code></pre>{_render_doc(entry.doc)}{members}</div>"
    )


def render_page(files: list[SourceFile], style: str, script: str) -> str:
    """Render the files into one HTML page with the style and script inlined.

    The page carries no timestamp, so the same source renders the same page.

    Example:
        render_page(collect_all(root), style, script)[:15]
        # -> '<!doctype html>'

    """
    sections = [C_API_SECTION, CPP_SECTION, PYTHON_SECTION]
    body = [_render_sidebar(files, sections), "<main><h1>UndeadLib API</h1>"]
    for section in sections:
        body.append(
            f'<section><h2 class="section-title">{html.escape(section)}</h2>'
        )
        for source in files:
            if source.section != section:
                continue
            body.append(
                f'<article class="file" id="{_slug(source.path)}">'
                f"<h3>{html.escape(source.path)}</h3>"
                f'<div class="overview">{_render_doc(source.overview)}</div>'
            )
            body.extend(
                _render_entry(source, entry) for entry in source.entries
            )
            body.append("</article>")
        body.append("</section>")
    body.append("</main>")
    return (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>UndeadLib API</title><style>{style}</style></head><body>"
        f"{''.join(body)}<script>{script}</script></body></html>\n"
    )


def main(arguments: list[str]) -> int:
    """Write the page, or with --check only report, and return the exit code.

    Example:
        main(["--root", ".", "--check"])  # -> 0 when everything is documented
        main(["--root", ".", "--out", "build/docs/api.html"])  # writes it

    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--out", type=Path)
    mode.add_argument("--check", action="store_true")
    parsed = parser.parse_args(arguments)

    files = collect_all(parsed.root.resolve())
    missing = undocumented(files)
    for name in missing:
        print(f"undocumented: {name}")
    if parsed.out is not None:
        page = render_page(
            files,
            STYLE.read_text(encoding="utf-8"),
            SCRIPT.read_text(encoding="utf-8"),
        )
        parsed.out.parent.mkdir(parents=True, exist_ok=True)
        parsed.out.write_text(page, encoding="utf-8")
        print(f"wrote {parsed.out}")
    entry_count = sum(len(source.entries) for source in files)
    print(
        f"{len(files)} files, {entry_count} declarations, "
        f"{len(missing)} undocumented"
    )
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
