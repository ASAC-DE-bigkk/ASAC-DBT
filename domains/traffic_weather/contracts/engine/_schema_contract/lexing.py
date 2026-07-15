"""Internal _schema_contract lexing responsibility."""

from __future__ import annotations

from .types import (
    BLOCK_SCALAR_RE,
    MAX_FILE_BYTES,
    MAX_LINE_COUNT,
    MAX_LINE_LENGTH,
    MAX_NESTING_DEPTH,
    MAX_SCALAR_LENGTH,
    ScanError,
    Token,
)


def _strip_comment(text: str, line: int) -> str:
    quote: str | None = None
    escaped = False
    index = 0
    while index < len(text):
        character = text[index]
        if quote == '"':
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                quote = None
        elif quote == "'":
            if character == "'":
                if index + 1 < len(text) and text[index + 1] == "'":
                    index += 1
                else:
                    quote = None
        elif character in {'"', "'"}:
            quote = character
        elif character == "#" and (index == 0 or text[index - 1].isspace()):
            return text[:index].rstrip()
        index += 1
    if quote is not None:
        raise ScanError("unterminated quoted scalar", line=line)
    return text.rstrip()


def _outside_quote_positions(text: str) -> list[tuple[int, str]]:
    positions: list[tuple[int, str]] = []
    quote: str | None = None
    escaped = False
    index = 0
    while index < len(text):
        character = text[index]
        if quote == '"':
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                quote = None
        elif quote == "'":
            if character == "'":
                if index + 1 < len(text) and text[index + 1] == "'":
                    index += 1
                else:
                    quote = None
        elif character in {'"', "'"}:
            quote = character
        else:
            positions.append((index, character))
        index += 1
    return positions


def _find_mapping_colon(text: str) -> int | None:
    depth = 0
    for index, character in _outside_quote_positions(text):
        if character in "[{":
            depth += 1
        elif character in "]}":
            depth -= 1
        elif (
            character == ":"
            and depth == 0
            and (index + 1 == len(text) or text[index + 1].isspace())
        ):
            return index
    return None


def _find_implicit_flow_mapping_colon(text: str) -> int | None:
    for index, character in _outside_quote_positions(text):
        if character != ":":
            continue
        if index + 1 == len(text) or text[index + 1].isspace():
            return index
    return None


def _find_plain_scalar_mapping_colon(text: str) -> int | None:
    for index, character in enumerate(text):
        if character == ":" and (index + 1 == len(text) or text[index + 1].isspace()):
            return index
    return None


def _split_flow_items(text: str) -> list[str]:
    items: list[str] = []
    start = 0
    quote: str | None = None
    escaped = False
    index = 0
    while index < len(text):
        character = text[index]
        if quote == '"':
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                quote = None
        elif quote == "'":
            if character == "'":
                if index + 1 < len(text) and text[index + 1] == "'":
                    index += 1
                else:
                    quote = None
        elif character in {'"', "'"}:
            quote = character
        elif character == ",":
            items.append(text[start:index].strip())
            start = index + 1
        index += 1
    items.append(text[start:].strip())
    return items


def _flow_bounds(text: str, line: int) -> tuple[int, int] | None:
    outside = _outside_quote_positions(text)
    openings = [(index, char) for index, char in outside if char in "[{"]
    closings = [(index, char) for index, char in outside if char in "]}"]
    if not openings and not closings:
        return None
    if not openings or not closings:
        raise ScanError("multiline or unbalanced flow collection", line=line)
    start, opener = openings[0]
    expected = "]" if opener == "[" else "}"
    depth = 0
    end: int | None = None
    for index, character in outside:
        if index < start:
            continue
        if character in "[{":
            depth += 1
            if depth > 1:
                raise ScanError("nested flow collections are unsupported", line=line)
        elif character in "]}":
            if depth == 0 or character != expected:
                raise ScanError("mismatched flow collection delimiter", line=line)
            depth -= 1
            if depth == 0:
                end = index
                break
    if depth or end is None:
        raise ScanError("multiline or unbalanced flow collection", line=line)
    if text[end + 1 :].strip():
        raise ScanError("content after flow collection is unsupported", line=line)
    if any(index > end for index, _ in openings + closings):
        raise ScanError("multiple flow collections are unsupported", line=line)
    return start, end


def _validate_lexical_content(content: str, line: int) -> None:
    candidate = content[2:] if content.startswith("- ") else content
    colon = _find_mapping_colon(candidate)
    candidate_key = candidate[:colon].strip() if colon is not None else None
    if candidate_key == "<<":
        raise ScanError("merge keys are unsupported", line=line)
    scalar_value = (
        candidate[colon + 1 :].lstrip() if colon is not None else candidate.lstrip()
    )
    if scalar_value.startswith(("&", "*", "!")):
        construct = {"&": "anchor", "*": "alias", "!": "tag"}[scalar_value[0]]
        raise ScanError(f"YAML {construct} node properties are unsupported", line=line)
    if scalar_value.startswith(("|", ">")) and not BLOCK_SCALAR_RE.fullmatch(
        scalar_value
    ):
        raise ScanError("malformed block scalar indicator", line=line)
    if scalar_value.startswith(("@", "`", "%", ",", "]", "}")):
        raise ScanError(
            "reserved YAML indicator cannot start a plain scalar", line=line
        )
    if scalar_value[:1] in {"?", "-", ":"} and (
        len(scalar_value) == 1 or scalar_value[1].isspace()
    ):
        raise ScanError(
            "reserved YAML indicator cannot start a plain scalar", line=line
        )
    if scalar_value.startswith(("[", "{", "]", "}")):
        _flow_bounds(scalar_value, line)


def _block_indicator(content: str) -> tuple[str, int, int | None] | None:
    effective_indent = 0
    candidate = content
    if candidate.startswith("- "):
        candidate = candidate[2:]
        effective_indent = 2
    colon = _find_mapping_colon(candidate)
    if colon is None:
        return None
    value = candidate[colon + 1 :].strip()
    if BLOCK_SCALAR_RE.fullmatch(value):
        explicit_indent = next(
            (int(character) for character in value if character.isdigit()), None
        )
        return value, effective_indent, explicit_indent
    return None


def _fold_block(lines: list[str], style: str, margin: int) -> str:
    if not lines:
        return ""
    content = [line[margin:] if line.strip() else "" for line in lines]
    if style == ">":
        return " ".join(part.strip() for part in content).strip()
    return "\n".join(content).rstrip("\n")


def _tokenize(text: str) -> list[Token]:
    encoded_size = len(text.encode("utf-8"))
    if encoded_size > MAX_FILE_BYTES:
        raise ScanError(
            f"file exceeds maximum size of {MAX_FILE_BYTES} UTF-8 bytes",
            code="INPUT_LIMIT_EXCEEDED",
        )
    for offset, character in enumerate(text):
        codepoint = ord(character)
        if (
            (codepoint < 0x20 and character not in {"\n", "\r", "\t"})
            or codepoint == 0x7F
            or (0x80 <= codepoint <= 0x9F and codepoint != 0x85)
        ):
            line = text.count("\n", 0, offset) + 1
            raise ScanError(
                "non-printable YAML control characters are unsupported", line=line
            )
    raw_lines = text.split("\n")
    if len(raw_lines) > MAX_LINE_COUNT:
        raise ScanError(
            f"file exceeds maximum line count of {MAX_LINE_COUNT}",
            code="INPUT_LIMIT_EXCEEDED",
        )
    for line_number, raw in enumerate(raw_lines, start=1):
        if "\t" in raw:
            raise ScanError("tabs are unsupported", line=line_number)
        if len(raw) > MAX_LINE_LENGTH:
            raise ScanError(
                f"line exceeds maximum length of {MAX_LINE_LENGTH} characters",
                line=line_number,
                code="INPUT_LIMIT_EXCEEDED",
            )

    tokens: list[Token] = []
    index = 0
    while index < len(raw_lines):
        raw = raw_lines[index]
        line_number = index + 1
        if not raw.strip() or raw.lstrip(" ").startswith("#"):
            index += 1
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        content = _strip_comment(raw[indent:], line_number)
        if not content:
            index += 1
            continue
        _validate_lexical_content(content, line_number)

        block = _block_indicator(content)
        block_value: str | None = None
        if block is not None:
            indicator, inline_offset, explicit_indent = block
            key_indent = indent + inline_offset
            block_lines: list[str] = []
            content_indent = (
                key_indent + explicit_indent if explicit_indent is not None else None
            )
            cursor = index + 1
            while cursor < len(raw_lines):
                candidate = raw_lines[cursor]
                candidate_indent = len(candidate) - len(candidate.lstrip(" "))
                if candidate.strip() and candidate_indent <= key_indent:
                    break
                if candidate.strip():
                    if content_indent is None:
                        content_indent = candidate_indent
                    elif candidate_indent < content_indent:
                        raise ScanError(
                            "block scalar content dedents below its required indentation",
                            line=cursor + 1,
                        )
                block_lines.append(candidate)
                cursor += 1
            margin = content_indent if content_indent is not None else key_indent + 1
            block_value = _fold_block(block_lines, indicator[0], margin)
            if len(block_value) > MAX_SCALAR_LENGTH:
                raise ScanError(
                    f"block scalar exceeds maximum length of {MAX_SCALAR_LENGTH} characters",
                    line=line_number,
                    code="INPUT_LIMIT_EXCEEDED",
                )
            index = cursor
        else:
            index += 1

        if content.startswith("- "):
            remainder = content[2:].strip()
            if _find_mapping_colon(remainder) is not None:
                tokens.append(Token(indent=indent, content="-", line=line_number))
                tokens.append(
                    Token(
                        indent=indent + 2,
                        content=remainder,
                        line=line_number,
                        block_value=block_value,
                    )
                )
                continue
        tokens.append(
            Token(
                indent=indent,
                content=content,
                line=line_number,
                block_value=block_value,
            )
        )

    indent_stack: list[int] = []
    for token in tokens:
        while indent_stack and token.indent < indent_stack[-1]:
            indent_stack.pop()
        if not indent_stack or token.indent > indent_stack[-1]:
            indent_stack.append(token.indent)
        depth = len(indent_stack) - 1
        if depth > MAX_NESTING_DEPTH:
            raise ScanError(
                f"YAML nesting exceeds maximum depth of {MAX_NESTING_DEPTH}",
                line=token.line,
                code="INPUT_LIMIT_EXCEEDED",
            )
    return tokens
