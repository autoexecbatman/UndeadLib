"""Read an ES module's exports and their JSDoc comments for the API page.

The module is read as text, never run. Comments, strings and template
literals are masked out first, so braces inside them do not move the depth
that decides what is top level and what is a class member. Regex literals
are not masked; a regex holding a quote, a brace or a comment opener can
mislead the reader.

Usage, from docs/:

    from pathlib import Path
    import api_page_js

    root = Path("D:/repo/UndeadLib")
    source = api_page_js.collect_js_module(root / "bindings/js/undead.mjs",
                                           root)  # module, then its root
    [entry.name for entry in source.entries][:2]
    # -> ['Connectivity', 'UndeadError']
    api_page_js.parse_jsdoc_comment("/** @returns {number} The count. */")
    # -> DocBlock([DocPart('fields', 'Returns', '',
    #              [Field('number', 'The count.')])])

Refusals: an export form other than const, class or function, an
unrecognised class member, or a JSDoc tag outside @file, @param, @returns,
@throws and @example raises ValueError naming it.
"""

import re
import textwrap
from dataclasses import dataclass
from pathlib import Path

from api_model import (
    DocBlock,
    DocPart,
    Entry,
    Field,
    SourceFile,
    add_field,
    comment_lines,
)

JS_SECTION = "JavaScript binding"

_KNOWN_TAGS = {"@file", "@param", "@returns", "@return", "@throws", "@example"}

_NAME = r"[A-Za-z_$][\w$]*"
_EXPORT_CONST = re.compile(rf"^export\s+const\s+({_NAME})")
_EXPORT_CLASS = re.compile(rf"^export\s+class\s+({_NAME})")
_EXPORT_FUNCTION = re.compile(
    rf"^export\s+(?:async\s+)?function\*?\s+({_NAME})"
)
_METHOD = re.compile(
    rf"^(static\s+)?(?:async\s+)?(?:get\s+|set\s+)?(#?{_NAME})\s*\("
)
_FIELD = re.compile(rf"^(?:static\s+)?(#?{_NAME})\s*(?:=|;)")


@dataclass
class _Comment:
    """A /** */ block: its text and the line it ends on, counted from 1."""

    raw: str
    end_line: int


@dataclass
class _Declaration:
    """A declaration read from one line, and the last line its head spans."""

    name: str
    kind: str
    signature: str
    last_line: int


@dataclass
class _Masked:
    """A module's lines with comments and string contents blanked out."""

    lines: list[str]
    comments: list[_Comment]


def _split_type(text: str) -> tuple[str, str]:
    """Split a leading {type} from the rest; braces nest inside the type.

    Example:
        _split_type("{{ a: number }} options - An object.")
        # -> ('{ a: number }', 'options - An object.')
        _split_type("plain - No type.")  # -> ('', 'plain - No type.')

    Raises:
        ValueError: If the type's braces never close.

    """
    if not text.startswith("{"):
        return "", text
    depth = 0
    for index, character in enumerate(text):
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            # The brace that returns to depth 0 closes the type.
            if depth == 0:
                return text[1:index].strip(), text[index + 1 :].strip()
    raise ValueError(f"unclosed JSDoc type: {text}")


def parse_jsdoc_comment(raw: str) -> DocBlock:
    """Parse a JSDoc comment's prose, @example blocks and tags into parts.

    @param, @returns and @throws become titled fields, a parameter named
    "name: type"; @file is dropped, since the page already names the file.
    An @example runs to the next tag or the end of the comment, and a line
    after a field continues it until a blank line.

    Example:
        parse_jsdoc_comment("/** @param {number} width - Cells per row. */")
        # -> DocBlock([DocPart('fields', 'Parameters', '',
        #              [Field('width: number', 'Cells per row.')])])
        parse_jsdoc_comment("/** @deprecated Gone. */")
        # raises ValueError: unknown JSDoc tag @deprecated

    Raises:
        ValueError: On a tag outside the five the page renders.

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

    # An open example becomes one code part, dedented as a block.
    def flush_code() -> None:
        example = textwrap.dedent("\n".join(code)).strip("\n")
        if example:
            parts.append(DocPart("code", "", example, []))
        code.clear()

    for line in comment_lines(raw):
        stripped = line.strip()
        is_tag = stripped.startswith("@")
        # Inside @example every line is kept as written until the next tag.
        if is_in_code and not is_tag:
            code.append(line)
            continue
        if is_in_code:
            flush_code()
            is_in_code = False
        # A blank line ends a paragraph and any field it continued.
        if not stripped:
            flush_prose()
            current = None
            continue
        if not is_tag:
            if current is not None:
                current.text = f"{current.text} {stripped}".strip()
            else:
                prose.append(stripped)
            continue
        tag, _, rest = stripped.partition(" ")
        rest = rest.strip()
        if tag not in _KNOWN_TAGS:
            raise ValueError(f"unknown JSDoc tag {tag}")
        flush_prose()
        current = None
        if tag == "@file":
            continue
        if tag == "@example":
            is_in_code = True
            # Text on the tag's own line is the example's first line.
            if rest:
                code.append(rest)
            continue
        type_text, rest = _split_type(rest)
        if tag == "@param":
            name, _, text = rest.partition(" ")
            label = f"{name}: {type_text}" if type_text else name
            current = Field(label, text.strip().removeprefix("-").strip())
            add_field(parts, "Parameters", current)
        elif tag in ("@returns", "@return"):
            current = Field(type_text, rest)
            add_field(parts, "Returns", current)
        else:
            current = Field(type_text, rest)
            add_field(parts, "Throws", current)
    if is_in_code:
        flush_code()
    flush_prose()
    return DocBlock(parts)


def _mask(text: str) -> _Masked:
    r"""Blank out comments and string contents, keeping every line's length.

    Example:
        _mask('a = "{"; /** B. */\n').lines
        # -> ['a = " ";          ']
        _mask('/** B. */\nx;\n').comments[0].end_line  # -> 1

    Raises:
        ValueError: On a comment or string that never closes.

    """
    masked = list(text)
    comments: list[_Comment] = []
    index = 0
    line = 1

    # Blank text[start:end], keeping newlines so lines stay aligned.
    def blank(start: int, end: int) -> None:
        for position in range(start, end):
            if masked[position] != "\n":
                masked[position] = " "

    while index < len(text):
        character = text[index]
        pair = text[index : index + 2]
        if character == "\n":
            line += 1
            index += 1
        elif pair == "//":
            end = text.find("\n", index)
            end = len(text) if end == -1 else end
            blank(index, end)
            index = end
        elif pair == "/*":
            end = text.find("*/", index + 2)
            if end == -1:
                raise ValueError(f"line {line}: unclosed comment")
            end += 2
            body = text[index:end]
            line += body.count("\n")
            # A JSDoc block opens with /**; /**/ is an empty plain comment.
            if body.startswith("/**") and body != "/**/":
                comments.append(_Comment(body, line))
            blank(index, end)
            index = end
        elif character in "\"'`":
            end = index + 1
            while end < len(text) and text[end] != character:
                # A backslash escapes whatever follows it, a quote included.
                end += 2 if text[end] == "\\" else 1
            if end >= len(text):
                raise ValueError(f"line {line}: unclosed string")
            line += text.count("\n", index, end)
            # The quotes stay; everything between them is blanked.
            blank(index + 1, end)
            index = end + 1
        else:
            index += 1
    return _Masked("".join(masked).splitlines(), comments)


def _signature(
    lines: list[str], masked: list[str], start: int
) -> tuple[str, int]:
    r"""Join lines from start up to the body's opening brace into one line.

    Returns the signature and the index of the line holding the brace.

    Example:
        _signature(["f(", "\ta,", ") {"], ["f(", "\ta,", ") {"], 0)
        # -> ('f(a)', 2)

    Raises:
        ValueError: If no brace opens a body before the end of the file.

    """
    pieces = []
    for index in range(start, len(lines)):
        brace = masked[index].find("{")
        if brace != -1:
            pieces.append(lines[index][:brace])
            joined = re.sub(r"\s+", " ", " ".join(pieces)).strip()
            # Parameters on their own lines leave a space and a trailing comma.
            joined = joined.replace("( ", "(").replace(", )", ")")
            return joined.replace(" )", ")"), index
        pieces.append(lines[index])
    raise ValueError(f"line {start + 1}: no body follows this declaration")


def _export_declaration(
    lines: list[str], masked: list[str], index: int, where: str
) -> _Declaration:
    """Read the top-level export on line index: a const, class or function.

    A one-line const keeps its value in the signature; a longer one keeps
    only its name.

    Example:
        _export_declaration(["export class A {"], ["export class A {"], 0,
                            "a.mjs:1")
        # -> _Declaration('A', 'class', 'export class A', 0)
        _export_declaration(["export default 1;"], ["export default 1;"],
                            0, "a.mjs:1")
        # raises ValueError: a.mjs:1: unrecognised export form: ...

    Raises:
        ValueError: On any other export form.

    """
    code = masked[index].strip()
    const_match = _EXPORT_CONST.match(code)
    if const_match:
        name = const_match.group(1)
        signature = (
            lines[index].strip().removesuffix(";")
            if code.endswith(";")
            else f"export const {name}"
        )
        return _Declaration(name, "const", signature, index)
    for pattern, kind in (
        (_EXPORT_CLASS, "class"),
        (_EXPORT_FUNCTION, "function"),
    ):
        match = pattern.match(code)
        if match:
            signature, last_line = _signature(lines, masked, index)
            return _Declaration(match.group(1), kind, signature, last_line)
    raise ValueError(f"{where}: unrecognised export form: {code}")


def _member_declaration(
    lines: list[str], masked: list[str], index: int, where: str
) -> _Declaration:
    r"""Read the class member on line index: a method or a field.

    Example:
        _member_declaration(["\tstatic load(url) {"],
                            ["\tstatic load(url) {"], 0, "a.mjs:1")
        # -> _Declaration('load', 'static method', 'static load(url)', 0)
        _member_declaration(["\t#wasm;"], ["\t#wasm;"], 0, "a.mjs:1")
        # -> _Declaration('#wasm', 'field', '#wasm', 0)

    Raises:
        ValueError: On a line that is neither.

    """
    code = masked[index].strip()
    method_match = _METHOD.match(code)
    if method_match:
        name = method_match.group(2)
        signature, last_line = _signature(lines, masked, index)
        if name == "constructor":
            kind = "constructor"
        elif method_match.group(1):
            kind = "static method"
        else:
            kind = "method"
        return _Declaration(name, kind, signature, last_line)
    field_match = _FIELD.match(code)
    if field_match:
        signature = lines[index].strip().removesuffix(";")
        return _Declaration(field_match.group(1), "field", signature, index)
    raise ValueError(f"{where}: unrecognised class member: {code}")


def collect_js_module(module: Path, root: Path) -> SourceFile:
    """List an ES module's exports and each exported class's public members.

    Example:
        source = collect_js_module(root / "bindings/js/undead.mjs", root)
        source.entries[-1].name  # -> 'UndeadLibrary.dijkstraMap'
        collect_js_module(default_export_module, root)
        # raises ValueError: bare.mjs:3: unrecognised export form: ...

    Raises:
        ValueError: On an export form, class member or JSDoc tag the page
            does not know, naming the file and line.

    """
    path = module.relative_to(root).as_posix()
    text = module.read_text(encoding="utf-8")
    lines = text.splitlines()
    masked = _mask(text)
    docs = {comment.end_line: comment.raw for comment in masked.comments}

    # The comment ending on the line directly above a declaration is its doc.
    def doc_above(index: int) -> DocBlock | None:
        raw = docs.get(index)
        return parse_jsdoc_comment(raw) if raw is not None else None

    entries: list[Entry] = []
    depth = 0
    class_name: str | None = None
    skip_until = -1
    for index in range(len(lines)):
        code = masked.lines[index].strip()
        depth_before = depth
        depth += code.count("{") - code.count("}")
        # A continuation line of a signature already read is not a declaration.
        if index <= skip_until or not code:
            continue
        where = f"{path}:{index + 1}"
        if depth_before == 0 and code.startswith("export"):
            found = _export_declaration(lines, masked.lines, index, where)
            class_name = found.name if found.kind == "class" else None
        elif class_name is not None and depth_before == 1 and code != "}":
            found = _member_declaration(lines, masked.lines, index, where)
            found.name = f"{class_name}.{found.name}"
        else:
            # The brace that returns to depth 0 closes the open class.
            if depth == 0:
                class_name = None
            continue
        skip_until = found.last_line
        # A #private member is read, so its body is skipped, but not listed.
        if "#" not in found.name:
            entries.append(
                Entry(
                    found.name,
                    found.kind,
                    found.signature,
                    index + 1,
                    doc_above(index),
                    [],
                )
            )

    first = masked.comments[0].raw if masked.comments else None
    is_file_block = first is not None and any(
        line.strip().startswith("@file") for line in comment_lines(first)
    )
    overview = parse_jsdoc_comment(first) if first and is_file_block else None
    return SourceFile(JS_SECTION, path, overview, entries)
