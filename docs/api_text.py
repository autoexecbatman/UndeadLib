r"""Read C-family source as masked text, for the readers that have no parser.

mask_source blanks comments and the contents of string literals, keeping
every line's length, so a brace inside either does not move the depth that
decides what is a declaration. It records each /** */ block and the line
it ends on. signature_head joins a declaration's head, possibly spread
over several lines, into one line. Used by api_page_js and api_page_cs.

Regex literals and verbatim, raw or nested interpolated strings are not
understood; a quote, brace or comment opener inside one can mislead it.

Usage:

    from api_text import mask_source, signature_head

    masked = mask_source('/** Doc. */\nf(\n\ta,\n) { return "}"; }\n')
    masked.comments[0].end_line  # -> 1, the line the comment ends on
    masked.lines[3]              # -> ') { return " "; }'
    lines = ["f(", "\ta,", ") { return 1; }"]
    signature_head(lines, masked.lines[1:], 0, ("{",))
    # -> ('f(a)', 2): the head, and the line the terminator is on
"""

import re
from dataclasses import dataclass


@dataclass
class Comment:
    """A /** */ block: its text and the line it ends on, counted from 1."""

    raw: str
    end_line: int


@dataclass
class MaskedSource:
    """A file's lines with comments and string contents blanked out."""

    lines: list[str]
    comments: list[Comment]


def mask_source(text: str) -> MaskedSource:
    r"""Blank out comments and string contents, keeping every line's length.

    Example:
        mask_source('a = "{"; /** B. */\n').lines
        # -> ['a = " ";          ']
        mask_source('/** B. */\nx;\n').comments[0].end_line  # -> 1

    Raises:
        ValueError: On a comment or string that never closes.

    """
    masked = list(text)
    comments: list[Comment] = []
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
                comments.append(Comment(body, line))
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
    return MaskedSource("".join(masked).splitlines(), comments)


def signature_head(
    lines: list[str],
    masked: list[str],
    start: int,
    terminators: tuple[str, ...],
) -> tuple[str, int]:
    r"""Join lines from start up to the first terminator into one line.

    Returns the head and the index of the line holding the terminator.
    Terminators are searched for in the masked lines, so one inside a
    string or comment does not end the head.

    Example:
        signature_head(["f(", "\ta,", ") {"], ["f(", "\ta,", ") {"], 0,
                       ("{",))
        # -> ('f(a)', 2)
        signature_head(["int X => 1;"], ["int X => 1;"], 0, ("{", "=>"))
        # -> ('int X', 0)

    Raises:
        ValueError: If no terminator follows before the end of the file.

    """
    pieces = []
    for index in range(start, len(lines)):
        found = [
            position
            for terminator in terminators
            if (position := masked[index].find(terminator)) != -1
        ]
        if found:
            pieces.append(lines[index][: min(found)])
            joined = re.sub(r"\s+", " ", " ".join(pieces)).strip()
            # Parameters on their own lines leave a space and a trailing comma.
            joined = joined.replace("( ", "(").replace(", )", ")")
            return joined.replace(" )", ")"), index
        pieces.append(lines[index])
    raise ValueError(f"line {start + 1}: no body follows this declaration")
