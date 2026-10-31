r"""Read C# public declarations and their XML comments for the API page.

The file is read as text, never compiled: api_text masks comments and
strings so braces inside them do not move the depth, and the depth decides
what is a type (0, under a file-scoped namespace) and what is a member (1).
Only public declarations are listed. An enum's values are listed inside it.
The overview is the // comment block that opens the file. XML comments are
parsed with xml.etree; the compiler already rejects malformed ones (CS1570).

Usage, from docs/:

    from pathlib import Path
    import api_page_cs

    root = Path("D:/repo/UndeadLib")
    source = api_page_cs.collect_cs_file(
        root / "bindings/csharp/Undead/UndeadLibrary.cs", root)
    [entry.name for entry in source.entries][:2]
    # -> ['UndeadLibrary', 'UndeadLibrary.UndeadLibrary']
    api_page_cs.parse_xml_doc(['<returns>The count.</returns>'])
    # -> DocBlock([DocPart('fields', 'Returns', '',
    #              [Field('', 'The count.')])])

Refusals: a block-scoped namespace, a nested public type, an unrecognised
public top-level line, or an XML tag outside summary, remarks, para,
example, code, param, returns, exception, c, see and paramref raises
ValueError naming it.
"""

import re
import textwrap
import xml.etree.ElementTree as ElementTree
from pathlib import Path

from api_model import DocBlock, DocPart, Entry, Field, SourceFile, add_field
from api_text import mask_source, signature_head

CS_SECTION = "C# binding"

_TYPE = re.compile(
    r"^(?:(?:public|internal|private|protected|sealed|static|abstract"
    r"|partial|unsafe|readonly|ref|file)\s+)*"
    r"(class|enum|struct|record|interface)\s+([A-Za-z_]\w*)"
)

# Where a member's head ends: its body, its expression body, or its end.
_MEMBER_TERMINATORS = ("{", "=>", ";")


def _normalized(text: str) -> str:
    r"""Collapse every run of whitespace to one space.

    Example:
        _normalized("  Walls\n stay  null. ")  # -> 'Walls stay null.'

    """
    return " ".join(text.split())


def _inline_child(child: ElementTree.Element) -> str:
    """Return the text an inline tag stands for: c, see or paramref.

    Example:
        _inline_child(ElementTree.fromstring('<see cref="A.B"/>'))  # -> 'A.B'

    Raises:
        ValueError: On any other tag.

    """
    if child.tag == "c":
        return _inline_text(child)
    if child.tag == "see":
        return child.get("cref") or child.get("langword") or ""
    if child.tag == "paramref":
        return child.get("name", "")
    raise ValueError(f"unknown XML doc tag <{child.tag}>")


def _inline_text(element: ElementTree.Element) -> str:
    """Return an element's text with its inline tags read as their text.

    Example:
        _inline_text(ElementTree.fromstring("<p>Pass <c>null</c>.</p>"))
        # -> 'Pass null.'

    Raises:
        ValueError: On a tag that is not inline.

    """
    pieces = [element.text or ""]
    for child in element:
        pieces.append(_inline_child(child))
        pieces.append(child.tail or "")
    return _normalized("".join(pieces))


def _add_block(parts: list[DocPart], element: ElementTree.Element) -> None:
    """Append a summary, remarks or example as paragraphs and code.

    Each para is its own paragraph, and code is dedented as one block.

    Example:
        parts: list[DocPart] = []
        _add_block(parts, ElementTree.fromstring(
            "<example>Call it:<code>Run();</code></example>"))
        # parts -> [DocPart('text', '', 'Call it:', []),
        #           DocPart('code', '', 'Run();', [])]

    Raises:
        ValueError: On a tag that is neither block nor inline.

    """
    pieces = [element.text or ""]

    # Text gathered since the last para or code becomes one paragraph.
    def flush() -> None:
        paragraph = _normalized("".join(pieces))
        if paragraph:
            parts.append(DocPart("text", "", paragraph, []))
        pieces.clear()

    for child in element:
        if child.tag == "para":
            flush()
            pieces.append(_inline_text(child))
            flush()
        elif child.tag == "code":
            flush()
            code = textwrap.dedent(child.text or "").strip("\n")
            parts.append(DocPart("code", "", code, []))
        else:
            pieces.append(_inline_child(child))
        pieces.append(child.tail or "")
    flush()


def parse_xml_doc(lines: list[str]) -> DocBlock:
    """Parse an XML comment's lines, without their ///, into parts.

    summary, remarks and example become paragraphs and code; param,
    returns and exception become titled fields, an exception named by its
    cref.

    Example:
        parse_xml_doc(['<param name="width">Cells per row.</param>'])
        # -> DocBlock([DocPart('fields', 'Parameters', '',
        #              [Field('width', 'Cells per row.')])])
        parse_xml_doc(["<inheritdoc/>"])
        # raises ValueError: unknown XML doc tag <inheritdoc>

    Raises:
        ValueError: On a tag outside the ones the page renders.

    """
    root = ElementTree.fromstring("<doc>" + "\n".join(lines) + "</doc>")
    parts: list[DocPart] = []
    for element in root:
        if element.tag in ("summary", "remarks", "example"):
            _add_block(parts, element)
        elif element.tag == "param":
            item = Field(element.get("name", ""), _inline_text(element))
            add_field(parts, "Parameters", item)
        elif element.tag == "returns":
            add_field(parts, "Returns", Field("", _inline_text(element)))
        elif element.tag == "exception":
            item = Field(element.get("cref", ""), _inline_text(element))
            add_field(parts, "Throws", item)
        else:
            raise ValueError(f"unknown XML doc tag <{element.tag}>")
    return DocBlock(parts)


def _doc_lines_above(lines: list[str], index: int) -> list[str] | None:
    """Return the /// lines directly above line index, without the ///.

    Example:
        _doc_lines_above(["/// <summary>A.</summary>", "public int A;"], 1)
        # -> ['<summary>A.</summary>']
        _doc_lines_above(["", "public int A;"], 1)  # -> None

    """
    start = index
    while start > 0 and lines[start - 1].strip().startswith("///"):
        start -= 1
    if start == index:
        return None
    # One space after /// is the comment's frame; the rest is content.
    return [line.strip()[3:].removeprefix(" ") for line in lines[start:index]]


def _overview(lines: list[str]) -> DocBlock | None:
    """Return the // block that opens the file as paragraphs, or None.

    Example:
        _overview(["// A file.", "//", "// Its use.", "", "namespace A;"])
        # -> DocBlock([DocPart('text', '', 'A file.', []),
        #              DocPart('text', '', 'Its use.', [])])
        _overview(["namespace A;"])  # -> None

    """
    paragraphs: list[str] = []
    current: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("//") or stripped.startswith("///"):
            break
        text = stripped[2:].strip()
        # An empty // line separates paragraphs.
        if text:
            current.append(text)
        elif current:
            paragraphs.append(" ".join(current))
            current = []
    if current:
        paragraphs.append(" ".join(current))
    if not paragraphs:
        return None
    return DocBlock([DocPart("text", "", text, []) for text in paragraphs])


def _wrapped(head: str) -> str:
    r"""Return a method head, one parameter per line when it is long.

    A head longer than 79 characters, the width the Python signatures are
    held to, breaks after the opening parenthesis. Only commas outside
    angle, round and square brackets separate parameters.

    Example:
        _wrapped("public void Run(int a)")  # -> 'public void Run(int a)'
        _wrapped("public void Fill(Dictionary<int, string> namesByIndex, "
                 "Func<int, int> transform)")
        # -> 'public void Fill(\n    Dictionary<int, string> namesByIndex,'
        #    '\n    Func<int, int> transform)'

    """
    if len(head) <= 79:
        return head
    open_index = head.index("(")
    close_index = head.rindex(")")
    inner = head[open_index + 1 : close_index]
    parameters = []
    depth = 0
    start = 0
    for position, character in enumerate(inner):
        if character in "<([":
            depth += 1
        elif character in ">)]":
            depth -= 1
        # A comma inside brackets belongs to a type, not the parameter list.
        elif character == "," and depth == 0:
            parameters.append(inner[start:position].strip())
            start = position + 1
    parameters.append(inner[start:].strip())
    listed = ",\n".join(f"    {parameter}" for parameter in parameters)
    return f"{head[: open_index + 1]}\n{listed}{head[close_index:]}"


def _member_entry(
    lines: list[str],
    masked: list[str],
    index: int,
    type_name: str,
    where: str,
) -> tuple[Entry, int]:
    r"""Read the public member on line index; return it and its head's end.

    Example:
        _member_entry(["\tpublic int Count => 3;"],
                      ["\tpublic int Count => 3;"], 0, "Box", "Box.cs:1")
        # -> (Entry('Box.Count', 'property', 'public int Count', 1,
        #           None, []), 0)

    Raises:
        ValueError: On a nested type.

    """
    code = masked[index].strip()
    if _TYPE.match(code):
        raise ValueError(f"{where}: nested types are not read: {code}")
    head, end = signature_head(lines, masked, index, _MEMBER_TERMINATORS)
    if "(" in head:
        name = head[: head.index("(")].split()[-1]
        kind = "constructor" if name == type_name else "method"
        head = _wrapped(head)
    else:
        name = head.split(" = ")[0].split()[-1]
        # The terminator that ended the head tells a field from a property.
        positions = {
            terminator: masked[end].find(terminator)
            for terminator in _MEMBER_TERMINATORS
            if terminator in masked[end]
        }
        first = min(positions, key=positions.__getitem__)
        kind = "field" if first == ";" else "property"
    doc_lines = _doc_lines_above(lines, index)
    doc = parse_xml_doc(doc_lines) if doc_lines is not None else None
    entry = Entry(f"{type_name}.{name}", kind, head, index + 1, doc, [])
    return entry, end


def _enum_member(lines: list[str], masked: list[str], index: int) -> Field:
    """Read one enum value as a field: its declaration and its summary.

    Example:
        _enum_member(["/// <summary>Four.</summary>", "FourWay = 4,"],
                     ["", "FourWay = 4,"], 1)
        # -> Field('FourWay = 4', 'Four.')

    """
    doc_lines = _doc_lines_above(lines, index)
    doc = parse_xml_doc(doc_lines) if doc_lines is not None else None
    text = " ".join(
        part.text for part in (doc.parts if doc else []) if part.kind == "text"
    )
    return Field(masked[index].strip().removesuffix(","), text)


def collect_cs_file(source: Path, root: Path) -> SourceFile:
    """List a C# file's public types and each one's public members.

    Example:
        source = collect_cs_file(
            root / "bindings/csharp/Undead/UndeadLibrary.cs", root)
        source.entries[-1].name  # -> 'UndeadLibrary.Dispose'

    Raises:
        ValueError: On a block-scoped namespace, a nested type, a public
            line that is not a type, or an unknown XML tag, naming the
            file and line.

    """
    path = source.relative_to(root).as_posix()
    lines = source.read_text(encoding="utf-8").splitlines()
    masked = mask_source("\n".join(lines)).lines
    entries: list[Entry] = []
    depth = 0
    type_entry: Entry | None = None
    skip_until = -1
    for index in range(len(lines)):
        code = masked[index].strip()
        depth_before = depth
        depth += code.count("{") - code.count("}")
        # A continuation of a head already read is not a declaration.
        if index <= skip_until or not code:
            continue
        where = f"{path}:{index + 1}"
        if depth_before == 0:
            type_entry = None
            if code.startswith("namespace") and not code.endswith(";"):
                raise ValueError(f"{where}: only file-scoped namespaces")
            match = _TYPE.match(code)
            # Values are read one per line, so a one-line enum would list none.
            if match and match.group(1) == "enum" and "}" in code:
                raise ValueError(f"{where}: write an enum one value per line")
            if match and code.startswith("public"):
                head, skip_until = signature_head(lines, masked, index, ("{",))
                doc_lines = _doc_lines_above(lines, index)
                doc = parse_xml_doc(doc_lines) if doc_lines else None
                type_entry = Entry(
                    match.group(2), match.group(1), head, index + 1, doc, []
                )
                entries.append(type_entry)
            elif code.startswith("public"):
                raise ValueError(f"{where}: unrecognised declaration: {code}")
            continue
        # Members sit at depth 1, inside a listed type.
        if depth_before != 1 or type_entry is None or code in ("{", "}"):
            continue
        if type_entry.kind == "enum":
            type_entry.members.append(_enum_member(lines, masked, index))
        elif code.startswith("public"):
            entry, skip_until = _member_entry(
                lines, masked, index, type_entry.name, where
            )
            entries.append(entry)
    return SourceFile(CS_SECTION, path, _overview(lines), entries)
