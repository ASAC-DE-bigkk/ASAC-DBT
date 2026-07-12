#!/usr/bin/env python3
"""Conservatively lint Korean descriptions in dbt source schema YAML files."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

try:
    from domains.traffic.contracts.scripts.artifact_io import write_utf8_stdout
except ModuleNotFoundError:  # Direct execution from scripts/contracts.
    from artifact_io import write_utf8_stdout


YAML_SUFFIXES = {".yml", ".yaml"}
HANGUL_RE = re.compile(r"[\u3131-\u318e\uac00-\ud7a3]")
BLOCK_SCALAR_RE = re.compile(r"^[|>](?:[+-]?[1-9]?|[1-9][+-]?)?$")
MAX_FILE_BYTES = 1_048_576
MAX_LINE_COUNT = 10_000
MAX_LINE_LENGTH = 16_384
MAX_SCALAR_LENGTH = 131_072
MAX_NESTING_DEPTH = 64
PLACEHOLDER_RE = re.compile(
    r"^(?:(?:todo|tbd|placeholder|pending|later|n/?a|not\s+yet|coming\s+soon)"
    r"(?:\s*(?:입니다|임|이다|예정|작성\s*예정|추후\s*작성))?|"
    r"(?:추후(?:\s*작성)?(?:\s*예정)?|나중에\s*작성(?:\s*예정)?|미정|미작성|작성\s*예정|보완\s*예정|준비\s*중)"
    r"(?:입니다|임|이다)?)\s*[.!?。]*$",
    re.IGNORECASE,
)
CLAIM_LIMITATIONS_KO = (
    "이 도구는 실제 relation 컬럼·타입·순서, SQL projection, grain, 최신 선택과 "
    "tie-break, reconciliation 또는 데이터 의미 정합성을 증명하지 않습니다."
)


@dataclass(frozen=True)
class Token:
    indent: int
    content: str
    line: int
    block_value: str | None = None


@dataclass
class MapEntry:
    key: str
    line: int
    value: "Node"


@dataclass
class Node:
    kind: str
    line: int
    value: str | None = None
    mapping: list[MapEntry] = field(default_factory=list)
    sequence: list["Node"] = field(default_factory=list)

    def entry(self, key: str) -> MapEntry | None:
        for item in self.mapping:
            if item.key == key:
                return item
        return None


class ScanError(Exception):
    def __init__(
        self,
        message: str,
        *,
        line: int | None = None,
        code: str = "UNSUPPORTED_YAML",
        lines: list[int] | None = None,
        key: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.line = line
        self.code = code
        self.lines = lines
        self.key = key


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
    candidate_key = (
        candidate[:colon].strip()
        if colon is not None
        else None
    )
    if candidate_key == "<<":
        raise ScanError("merge keys are unsupported", line=line)
    scalar_value = candidate[colon + 1 :].lstrip() if colon is not None else candidate.lstrip()
    if scalar_value.startswith(("&", "*", "!")):
        construct = {"&": "anchor", "*": "alias", "!": "tag"}[scalar_value[0]]
        raise ScanError(f"YAML {construct} node properties are unsupported", line=line)
    if scalar_value.startswith(("|", ">")) and not BLOCK_SCALAR_RE.fullmatch(scalar_value):
        raise ScanError("malformed block scalar indicator", line=line)
    if scalar_value.startswith(("@", "`", "%", ",", "]", "}")):
        raise ScanError("reserved YAML indicator cannot start a plain scalar", line=line)
    if scalar_value[:1] in {"?", "-", ":"} and (
        len(scalar_value) == 1 or scalar_value[1].isspace()
    ):
        raise ScanError("reserved YAML indicator cannot start a plain scalar", line=line)
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
        explicit_indent = next((int(character) for character in value if character.isdigit()), None)
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
            raise ScanError("non-printable YAML control characters are unsupported", line=line)
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
            content_indent = key_indent + explicit_indent if explicit_indent is not None else None
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
        tokens.append(Token(indent=indent, content=content, line=line_number, block_value=block_value))

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


def _decode_yaml_double_quoted(value: str, line: int) -> str:
    simple_escapes = {
        '"': '"',
        "/": "/",
        "\\": "\\",
        "t": "\t",
        "n": "\n",
        "r": "\r",
        " ": " ",
        "N": "\u0085",
        "_": "\u00a0",
        "L": "\u2028",
        "P": "\u2029",
    }
    decoded: list[str] = []
    index = 0
    while index < len(value):
        character = value[index]
        if character != "\\":
            decoded.append(character)
            index += 1
            continue
        if index + 1 >= len(value):
            raise ScanError("malformed double-quoted scalar: trailing backslash", line=line)
        escape = value[index + 1]
        if escape in {"0", "a", "b", "v", "f", "e"}:
            raise ScanError("double-quoted escape decodes to a forbidden control", line=line)
        if escape in simple_escapes:
            decoded.append(simple_escapes[escape])
            index += 2
            continue
        widths = {"x": 2, "u": 4, "U": 8}
        width = widths.get(escape)
        if width is None:
            raise ScanError(
                f"malformed double-quoted scalar: unknown escape \\{escape}",
                line=line,
            )
        start = index + 2
        digits = value[start : start + width]
        if len(digits) != width or not re.fullmatch(r"[0-9A-Fa-f]+", digits):
            raise ScanError(
                f"malformed double-quoted scalar: \\{escape} requires {width} hex digits",
                line=line,
            )
        codepoint = int(digits, 16)
        if codepoint > 0x10FFFF or 0xD800 <= codepoint <= 0xDFFF:
            raise ScanError("double-quoted escape is not a Unicode scalar value", line=line)
        if (
            codepoint < 0x20
            or codepoint == 0x7F
            or (0x80 <= codepoint <= 0x9F and codepoint != 0x85)
        ):
            raise ScanError("double-quoted escape decodes to a forbidden control", line=line)
        decoded.append(chr(codepoint))
        index = start + width
    return "".join(decoded)


def _decode_scalar(text: str, line: int) -> str:
    value = text.strip()
    if not value:
        return ""
    if value.startswith("'"):
        if len(value) < 2 or not value.endswith("'"):
            raise ScanError("malformed single-quoted scalar", line=line)
        decoded = value[1:-1].replace("''", "'")
        if len(decoded) > MAX_SCALAR_LENGTH:
            raise ScanError(
                f"scalar exceeds maximum length of {MAX_SCALAR_LENGTH} characters",
                line=line,
                code="INPUT_LIMIT_EXCEEDED",
            )
        return decoded
    if value.startswith('"'):
        if len(value) < 2 or not value.endswith('"'):
            raise ScanError("malformed double-quoted scalar", line=line)
        decoded = _decode_yaml_double_quoted(value[1:-1], line)
        if len(decoded) > MAX_SCALAR_LENGTH:
            raise ScanError(
                f"scalar exceeds maximum length of {MAX_SCALAR_LENGTH} characters",
                line=line,
                code="INPUT_LIMIT_EXCEEDED",
            )
        return decoded
    if value[0] in "'\"" or value[-1] in "'\"":
        raise ScanError("malformed quoted scalar", line=line)
    if value.startswith(("&", "*", "!")):
        construct = {"&": "anchor", "*": "alias", "!": "tag"}[value[0]]
        raise ScanError(f"YAML {construct} node properties are unsupported", line=line)
    if value.startswith(("@", "`", "%", ",", "[", "{", "]", "}", "|", ">")):
        raise ScanError("reserved YAML indicator cannot start a plain scalar", line=line)
    if value[:1] in {"?", "-", ":"} and (len(value) == 1 or value[1].isspace()):
        raise ScanError("reserved YAML indicator cannot start a plain scalar", line=line)
    if _find_plain_scalar_mapping_colon(value) is not None:
        raise ScanError("plain scalar contains an extra YAML mapping separator", line=line)
    if len(value) > MAX_SCALAR_LENGTH:
        raise ScanError(
            f"scalar exceeds maximum length of {MAX_SCALAR_LENGTH} characters",
            line=line,
            code="INPUT_LIMIT_EXCEEDED",
        )
    return value


def _parse_flow(text: str, line: int) -> Node:
    bounds = _flow_bounds(text, line)
    if bounds is None or bounds[0] != 0 or bounds[1] != len(text) - 1:
        raise ScanError("flow collection must be the complete scalar value", line=line)
    inner = text[1:-1].strip()
    if text[0] == "[":
        if not inner:
            return Node(kind="seq", line=line)
        items = _split_flow_items(inner)
        if any(not item for item in items):
            raise ScanError("empty flow-list item", line=line)
        for item in items:
            if _find_implicit_flow_mapping_colon(item) is not None:
                raise ScanError("implicit mappings in flow sequences are unsupported", line=line)
            if item == "-" or item.startswith("- "):
                raise ScanError("implicit sequences in flow sequences are unsupported", line=line)
        return Node(
            kind="seq",
            line=line,
            sequence=[Node(kind="scalar", line=line, value=_decode_scalar(item, line)) for item in items],
        )

    node = Node(kind="map", line=line)
    if not inner:
        return node
    seen: dict[str, int] = {}
    for item in _split_flow_items(inner):
        colon = _find_mapping_colon(item)
        if colon is None:
            raise ScanError("flow-map item lacks a mapping separator", line=line)
        key = _decode_scalar(item[:colon], line)
        raw_value = item[colon + 1 :].strip()
        if not key or not raw_value:
            raise ScanError("flow-map key and value must be scalar", line=line)
        if _find_implicit_flow_mapping_colon(raw_value) is not None:
            raise ScanError("implicit mappings in flow-map values are unsupported", line=line)
        if raw_value == "-" or raw_value.startswith("- "):
            raise ScanError("implicit sequences in flow-map values are unsupported", line=line)
        if key in seen:
            raise ScanError(
                f"duplicate mapping key '{key}'",
                code="DUPLICATE_MAPPING_KEY",
                lines=[seen[key], line],
                key=key,
            )
        seen[key] = line
        node.mapping.append(
            MapEntry(key=key, line=line, value=Node(kind="scalar", line=line, value=_decode_scalar(raw_value, line)))
        )
    return node


def _parse_value(token: Token, raw_value: str) -> Node:
    value = raw_value.strip()
    if BLOCK_SCALAR_RE.fullmatch(value):
        return Node(kind="scalar", line=token.line, value=token.block_value or "")
    if value.startswith(("[", "{")):
        return _parse_flow(value, token.line)
    return Node(kind="scalar", line=token.line, value=_decode_scalar(value, token.line))


def _parse_mapping(tokens: list[Token], index: int, indent: int) -> tuple[Node, int]:
    node = Node(kind="map", line=tokens[index].line)
    seen: dict[str, int] = {}
    while index < len(tokens):
        token = tokens[index]
        if token.indent < indent:
            break
        if token.indent > indent:
            raise ScanError("unclassified indentation", line=token.line)
        if token.content == "-" or token.content.startswith("- "):
            raise ScanError("mapping and sequence entries share one indentation", line=token.line)
        colon = _find_mapping_colon(token.content)
        if colon is None:
            raise ScanError("line is not a block mapping entry", line=token.line)
        key = _decode_scalar(token.content[:colon], token.line)
        if not key:
            raise ScanError("empty mapping key", line=token.line)
        if key == "<<":
            raise ScanError("merge keys are unsupported", line=token.line)
        if key in seen:
            raise ScanError(
                f"duplicate mapping key '{key}'",
                code="DUPLICATE_MAPPING_KEY",
                lines=[seen[key], token.line],
                key=key,
            )
        seen[key] = token.line
        raw_value = token.content[colon + 1 :].strip()
        index += 1
        if raw_value:
            value = _parse_value(token, raw_value)
            if index < len(tokens) and tokens[index].indent > indent:
                raise ScanError("scalar mapping value has nested indentation", line=tokens[index].line)
        elif index < len(tokens) and tokens[index].indent > indent:
            value, index = _parse_block(tokens, index, tokens[index].indent)
        else:
            value = Node(kind="scalar", line=token.line, value="")
        node.mapping.append(MapEntry(key=key, line=token.line, value=value))
    return node, index


def _parse_sequence(tokens: list[Token], index: int, indent: int) -> tuple[Node, int]:
    node = Node(kind="seq", line=tokens[index].line)
    while index < len(tokens):
        token = tokens[index]
        if token.indent < indent:
            break
        if token.indent > indent:
            raise ScanError("unclassified sequence indentation", line=token.line)
        if token.content == "-":
            index += 1
            if index >= len(tokens) or tokens[index].indent <= indent:
                raise ScanError("sequence item has no value", line=token.line)
            value, index = _parse_block(tokens, index, tokens[index].indent)
        elif token.content.startswith("- "):
            value = _parse_value(token, token.content[2:])
            index += 1
            if index < len(tokens) and tokens[index].indent > indent:
                raise ScanError("scalar sequence item has nested indentation", line=tokens[index].line)
        else:
            raise ScanError("mapping and sequence entries share one indentation", line=token.line)
        node.sequence.append(value)
    return node, index


def _parse_block(tokens: list[Token], index: int, indent: int) -> tuple[Node, int]:
    if tokens[index].indent != indent:
        raise ScanError("malformed block indentation", line=tokens[index].line)
    if tokens[index].content == "-" or tokens[index].content.startswith("- "):
        return _parse_sequence(tokens, index, indent)
    return _parse_mapping(tokens, index, indent)


def _parse_yaml_subset(text: str) -> Node:
    tokens = _tokenize(text)
    if not tokens:
        return Node(kind="map", line=1)
    if tokens[0].indent != 0:
        raise ScanError("root content must not be indented", line=tokens[0].line)
    root, index = _parse_block(tokens, 0, 0)
    if index != len(tokens):
        raise ScanError("scanner did not account for every structural line", line=tokens[index].line)
    if root.kind != "map":
        raise ScanError("schema root must be a block mapping", line=root.line)
    return root


def _scalar(entry: MapEntry | None, *, context: str) -> str | None:
    if entry is None:
        return None
    if entry.value.kind != "scalar":
        raise ScanError(f"{context} must be a scalar", line=entry.line)
    return entry.value.value or ""


def _normal_identifier(value: str) -> str:
    return "".join(
        character.casefold()
        for character in unicodedata.normalize("NFKC", value)
        if character.isalnum()
    )


PLACEHOLDER_WRAPPERS = (
    ("**", "**"),
    ("__", "__"),
    ("(", ")"),
    ("【", "】"),
    ("「", "」"),
    ("『", "』"),
    ("`", "`"),
    ("'", "'"),
    ('"', '"'),
    ("“", "”"),
    ("‘", "’"),
)
PLACEHOLDER_WRAPPER_SUFFIXES = ("입니다", "이다", "임", "예정", "")


def _unwrap_placeholder_grammar(value: str) -> str:
    for suffix in PLACEHOLDER_WRAPPER_SUFFIXES:
        if suffix and not value.endswith(suffix):
            continue
        core = value[: -len(suffix)].strip() if suffix else value.strip()
        changed = False
        while True:
            for opening, closing in PLACEHOLDER_WRAPPERS:
                if core.startswith(opening) and core.endswith(closing):
                    core = core[len(opening) : -len(closing)].strip()
                    changed = True
                    break
            else:
                break
        if changed:
            return f"{core}{suffix}"
    return value


def _is_single_placeholder(value: str) -> bool:
    without_terminal = value.strip().rstrip(".!?。！？")
    return bool(PLACEHOLDER_RE.fullmatch(_unwrap_placeholder_grammar(without_terminal)))


def _is_placeholder_description(value: str) -> bool:
    normalized = unicodedata.normalize("NFKC", value).strip()
    if _is_single_placeholder(normalized):
        return True
    segments = re.split(r"\s*(?:/|:|[-–—·])\s*", normalized)
    return len(segments) > 1 and all(
        segment and _is_single_placeholder(segment) for segment in segments
    )


def _description_evidence(
    *,
    path: str,
    resource_kind: str,
    resource_name: str,
    entity_kind: str,
    identifier: str,
    description: MapEntry | None,
    entity_line: int,
    column: str | None = None,
) -> tuple[dict[str, object], dict[str, object] | None]:
    evidence: dict[str, object] = {
        "accounted": True,
        "entity_kind": entity_kind,
        "expected": True,
        "field": "description",
        "file": path,
        "language_status": "MISSING",
        "present": description is not None,
        "resource_kind": resource_kind,
        "resource_name": resource_name,
        "scanned": True,
    }
    if column is not None:
        evidence["column"] = column
    if description is None:
        error = {
            "code": "MISSING_DESCRIPTION",
            "entity_kind": entity_kind,
            "field": "description",
            "file": path,
            "line": entity_line,
            "message": f"missing description for {entity_kind} '{identifier}'",
            "resource_kind": resource_kind,
            "resource_name": resource_name,
        }
        if column is not None:
            error["column"] = column
        return evidence, error
    if description.value.kind != "scalar":
        raise ScanError("description must be a scalar", line=description.line)
    value = description.value.value or ""
    evidence["line"] = description.line
    evidence["language_status"] = "PASS"
    evidence["value"] = value

    code: str | None = None
    reason: str | None = None
    if _is_placeholder_description(value):
        code, reason = "PLACEHOLDER_DESCRIPTION", "description is a placeholder"
        evidence["language_status"] = "PLACEHOLDER"
    elif _normal_identifier(value) == _normal_identifier(identifier):
        code, reason = "IDENTIFIER_ONLY_DESCRIPTION", "description only repeats its identifier"
        evidence["language_status"] = "IDENTIFIER_ONLY"
    elif not HANGUL_RE.search(value):
        code, reason = "DESCRIPTION_LANGUAGE", "description does not contain Hangul"
        evidence["language_status"] = "MISSING_HANGUL"
    if code is None:
        return evidence, None
    error = {
        "code": code,
        "entity_kind": entity_kind,
        "field": "description",
        "file": path,
        "line": description.line,
        "message": reason,
        "resource_kind": resource_kind,
        "resource_name": resource_name,
    }
    if column is not None:
        error["column"] = column
    return evidence, error


def _is_selected(name: str, selected: set[str] | None) -> bool:
    return selected is None or name in selected


def _scan_columns(
    resource: Node,
    *,
    path: str,
    resource_kind: str,
    resource_name: str,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    descriptions: list[dict[str, object]] = []
    errors: list[dict[str, object]] = []
    columns_entry = resource.entry("columns")
    if columns_entry is None:
        return descriptions, errors
    if columns_entry.value.kind != "seq":
        raise ScanError("columns must be a block sequence", line=columns_entry.line)
    seen: dict[str, int] = {}
    for column_node in columns_entry.value.sequence:
        if column_node.kind != "map":
            raise ScanError(
                "column item must be a mapping",
                line=column_node.line,
                code="MISSING_COLUMN_NAME",
            )
        name_entry = column_node.entry("name")
        column_name = _scalar(name_entry, context="column name")
        if not column_name or name_entry is None:
            errors.append(
                {
                    "code": "MISSING_COLUMN_NAME",
                    "file": path,
                    "line": column_node.line,
                    "message": f"column in {resource_kind} '{resource_name}' has no scalar name",
                    "resource_kind": resource_kind,
                    "resource_name": resource_name,
                }
            )
            continue
        if column_name in seen:
            errors.append(
                {
                    "code": "DUPLICATE_COLUMN",
                    "column": column_name,
                    "file": path,
                    "lines": [seen[column_name], name_entry.line],
                    "message": f"duplicate column '{column_name}' in {resource_kind} '{resource_name}'",
                    "resource_kind": resource_kind,
                    "resource_name": resource_name,
                }
            )
        else:
            seen[column_name] = name_entry.line
        evidence, error = _description_evidence(
            path=path,
            resource_kind=resource_kind,
            resource_name=resource_name,
            entity_kind="column",
            identifier=column_name,
            description=column_node.entry("description"),
            entity_line=name_entry.line,
            column=column_name,
        )
        descriptions.append(evidence)
        if error:
            errors.append(error)
    return descriptions, errors


def _scan_resource(
    node: Node,
    *,
    path: str,
    kind: str,
    name: str,
    name_line: int,
) -> tuple[dict[str, object], list[dict[str, object]], list[dict[str, object]]]:
    resource = {"file": path, "kind": kind, "line": name_line, "name": name}
    description, error = _description_evidence(
        path=path,
        resource_kind=kind,
        resource_name=name,
        entity_kind="resource",
        identifier=name,
        description=node.entry("description"),
        entity_line=name_line,
    )
    descriptions = [description]
    errors = [error] if error else []
    column_descriptions, column_errors = _scan_columns(
        node, path=path, resource_kind=kind, resource_name=name
    )
    descriptions.extend(column_descriptions)
    errors.extend(column_errors)
    return resource, descriptions, errors


def _named_items(entry: MapEntry, context: str) -> list[tuple[Node, str, int]]:
    if entry.value.kind != "seq":
        raise ScanError(f"{context} must be a block sequence", line=entry.line)
    result: list[tuple[Node, str, int]] = []
    for node in entry.value.sequence:
        if node.kind != "map":
            raise ScanError(
                f"{context} item must be a mapping",
                line=node.line,
                code="MISSING_RESOURCE_NAME",
            )
        name_entry = node.entry("name")
        name = _scalar(name_entry, context=f"{context} name")
        if not name or name_entry is None:
            raise ScanError(
                f"{context} item requires a scalar name",
                line=node.line,
                code="MISSING_RESOURCE_NAME",
            )
        result.append((node, name, name_entry.line))
    return result


def _duplicate_resource_error(
    *, path: str, kind: str, name: str, first_line: int, second_line: int
) -> dict[str, object]:
    return {
        "code": "DUPLICATE_RESOURCE",
        "file": path,
        "lines": [first_line, second_line],
        "message": f"duplicate {kind} resource '{name}'",
        "resource_kind": kind,
        "resource_name": name,
    }


def _extract_resources(
    root: Node, path: str, selected: set[str] | None
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], set[str]]:
    resources: list[dict[str, object]] = []
    descriptions: list[dict[str, object]] = []
    errors: list[dict[str, object]] = []
    discovered: set[str] = set()

    for section, kind in (("models", "model"), ("seeds", "seed")):
        section_entry = root.entry(section)
        if section_entry is None:
            continue
        items = _named_items(section_entry, section)
        seen: dict[str, int] = {}
        for node, name, line in items:
            discovered.add(name)
            selected_here = _is_selected(name, selected)
            if selected_here and name in seen:
                errors.append(
                    _duplicate_resource_error(
                        path=path,
                        kind=kind,
                        name=name,
                        first_line=seen[name],
                        second_line=line,
                    )
                )
            elif selected_here:
                seen[name] = line
            if not selected_here:
                continue
            resource, evidence, resource_errors = _scan_resource(
                node, path=path, kind=kind, name=name, name_line=line
            )
            resources.append(resource)
            descriptions.extend(evidence)
            errors.extend(resource_errors)

    sources_entry = root.entry("sources")
    if sources_entry is not None:
        sources = _named_items(sources_entry, "sources")
        seen_sources: dict[str, int] = {}
        for source_node, source_name, source_line in sources:
            canonical_source = f"source:{source_name}"
            discovered.add(canonical_source)
            source_selected = _is_selected(canonical_source, selected)
            if source_selected and source_name in seen_sources:
                errors.append(
                    _duplicate_resource_error(
                        path=path,
                        kind="source",
                        name=canonical_source,
                        first_line=seen_sources[source_name],
                        second_line=source_line,
                    )
                )
            elif source_selected:
                seen_sources[source_name] = source_line
            if source_selected:
                resource, evidence, resource_errors = _scan_resource(
                    source_node,
                    path=path,
                    kind="source",
                    name=canonical_source,
                    name_line=source_line,
                )
                resources.append(resource)
                descriptions.extend(evidence)
                errors.extend(resource_errors)

            tables_entry = source_node.entry("tables")
            if tables_entry is None:
                continue
            tables = _named_items(tables_entry, f"tables for source {source_name}")
            seen_tables: dict[str, int] = {}
            for table_node, table_name, table_line in tables:
                canonical_table = f"source:{source_name}.{table_name}"
                discovered.add(canonical_table)
                table_selected = _is_selected(canonical_table, selected)
                if table_selected and table_name in seen_tables:
                    errors.append(
                        _duplicate_resource_error(
                            path=path,
                            kind="source_table",
                            name=canonical_table,
                            first_line=seen_tables[table_name],
                            second_line=table_line,
                        )
                    )
                elif table_selected:
                    seen_tables[table_name] = table_line
                if not table_selected:
                    continue
                resource, evidence, resource_errors = _scan_resource(
                    table_node,
                    path=path,
                    kind="source_table",
                    name=canonical_table,
                    name_line=table_line,
                )
                resources.append(resource)
                descriptions.extend(evidence)
                errors.extend(resource_errors)
    return resources, descriptions, errors, discovered


def _error_sort_key(error: dict[str, object]) -> tuple[object, ...]:
    lines = error.get("lines")
    line = lines[0] if isinstance(lines, list) and lines else error.get("line", 0)
    files = error.get("files")
    file_name = (
        files[0]
        if isinstance(files, list) and files
        else error.get("file", error.get("path", ""))
    )
    return (
        file_name,
        line,
        error.get("code", ""),
        error.get("resource_name", ""),
        error.get("column", ""),
    )


def _proof_fields(
    *, status: str, errors: Iterable[dict[str, object]], files_complete: bool
) -> dict[str, object]:
    error_codes = {str(error.get("code", "")) for error in errors}
    uniqueness_pass = (
        status != "ERROR"
        and files_complete
        and not {
            "DUPLICATE_COLUMN",
            "DUPLICATE_RESOURCE",
            "MISSING_COLUMN_NAME",
            "MISSING_RESOURCE_NAME",
        }
        & error_codes
    )
    return {
        "claim_limitations_ko": CLAIM_LIMITATIONS_KO,
        "proof": {
            "data_contract": "NOT_RUN",
            "declared_contract": "PASS" if status == "PASS" else "FAIL",
            "manual_semantic_review": "REQUIRED",
            "physical_contract": "NOT_RUN",
            "source_yaml_uniqueness": "PASS" if uniqueness_pass else "FAIL",
        },
        "proof_scope": "source_yaml_declaration",
    }


def _empty_report(status: str, errors: list[dict[str, object]]) -> dict[str, object]:
    report: dict[str, object] = {
        "descriptions": [],
        "errors": sorted(errors, key=_error_sort_key),
        "files": [],
        "required_language": "ko-KR",
        "resources": [],
        "status": status,
        "summary": {
            "coverage_percentage": 0.0,
            "description_fields_accounted": 0,
            "description_fields_expected": 0,
            "description_fields_present": 0,
            "description_fields_unaccounted": 0,
            "error_count": len(errors),
            "files_scanned": 0,
            "files_total": 0,
            "resources_scanned": 0,
            "resources_total": 0,
            "resources_unaccounted": 0,
        },
    }
    report.update(_proof_fields(status=status, errors=errors, files_complete=False))
    return report


def _nearest_project_scope(path: Path, fallback_scope: Path) -> str:
    for ancestor in (path.parent, *path.parents[1:]):
        marker = ancestor / "dbt_project.yml"
        if marker.is_file() and not marker.is_symlink():
            return ancestor.resolve().as_posix()
    return fallback_scope.as_posix()


def _cross_file_duplicate_errors(
    resources: Iterable[dict[str, object]],
) -> list[dict[str, object]]:
    first_by_identity: dict[tuple[str, str, str], dict[str, object]] = {}
    errors: list[dict[str, object]] = []
    ordered = sorted(
        resources,
        key=lambda item: (
            str(item["project_scope"]),
            str(item["kind"]),
            str(item["name"]),
            str(item["file"]),
            int(item["line"]),
        ),
    )
    for resource in ordered:
        identity = (
            str(resource["project_scope"]),
            str(resource["kind"]),
            str(resource["name"]),
        )
        first = first_by_identity.get(identity)
        if first is None:
            first_by_identity[identity] = resource
            continue
        if first["file"] == resource["file"]:
            continue
        files = [str(first["file"]), str(resource["file"])]
        lines = [int(first["line"]), int(resource["line"])]
        errors.append(
            {
                "code": "DUPLICATE_RESOURCE",
                "file": files[0],
                "files": files,
                "lines": lines,
                "message": (
                    f"duplicate {resource['kind']} resource '{resource['name']}' "
                    "across schema files in one dbt project"
                ),
                "project_scope": str(resource["project_scope"]),
                "resource_kind": str(resource["kind"]),
                "resource_name": str(resource["name"]),
            }
        )
    return errors


def _discover_files(schema_roots: Iterable[str | Path]) -> tuple[list[Path], list[dict[str, object]]]:
    paths: set[Path] = set()
    errors: list[dict[str, object]] = []
    roots = sorted(
        {Path(root).expanduser().absolute() for root in schema_roots},
        key=lambda path: path.as_posix(),
    )
    if not roots:
        return [], [{"code": "INVALID_ROOT", "message": "at least one schema root is required"}]
    for requested_root in roots:
        if requested_root.is_symlink():
            errors.append(
                {
                    "code": "PATH_UNSAFE",
                    "message": f"schema root symlinks are unsupported: {requested_root.as_posix()}",
                    "path": requested_root.as_posix(),
                }
            )
            continue
        if not requested_root.exists():
            errors.append(
                {
                    "code": "INVALID_ROOT",
                    "message": f"schema root does not exist: {requested_root.as_posix()}",
                    "path": requested_root.as_posix(),
                }
            )
            continue
        try:
            root = requested_root.resolve(strict=True)
        except OSError as error:
            errors.append(
                {
                    "code": "IO_ERROR",
                    "message": f"cannot resolve schema root {requested_root.as_posix()}: {error}",
                    "path": requested_root.as_posix(),
                }
            )
            continue

        if root.is_file():
            if root.suffix.lower() not in YAML_SUFFIXES:
                errors.append(
                    {
                        "code": "INVALID_ROOT",
                        "message": f"schema root file is not YAML: {root.as_posix()}",
                        "path": root.as_posix(),
                    }
                )
            else:
                paths.add(root)
        elif root.is_dir():
            try:
                candidates = sorted(root.rglob("*"), key=lambda path: path.as_posix())
                for candidate in candidates:
                    if candidate.is_symlink():
                        errors.append(
                            {
                                "code": "PATH_UNSAFE",
                                "message": f"symlinks under schema roots are unsupported: {candidate.as_posix()}",
                                "path": candidate.as_posix(),
                            }
                        )
                        continue
                    if not candidate.is_file() or candidate.suffix.lower() not in YAML_SUFFIXES:
                        continue
                    resolved_candidate = candidate.resolve(strict=True)
                    try:
                        resolved_candidate.relative_to(root)
                    except ValueError:
                        errors.append(
                            {
                                "code": "PATH_UNSAFE",
                                "message": f"discovered YAML escapes schema root: {candidate.as_posix()}",
                                "path": candidate.as_posix(),
                            }
                        )
                        continue
                    paths.add(resolved_candidate)
            except OSError as error:
                errors.append(
                    {
                        "code": "IO_ERROR",
                        "message": f"cannot discover YAML under {root.as_posix()}: {error}",
                        "path": root.as_posix(),
                    }
                )
        else:
            errors.append(
                {
                    "code": "INVALID_ROOT",
                    "message": f"schema root is neither a file nor directory: {root.as_posix()}",
                    "path": root.as_posix(),
                }
            )
    if not errors and not paths:
        errors.append({"code": "INVALID_ROOT", "message": "schema roots contain no .yml or .yaml files"})
    return sorted(paths, key=lambda path: path.as_posix()), errors


def lint_schema_contracts(
    schema_roots: Iterable[str | Path],
    resources: Iterable[str] | None = None,
    required_language: str = "ko-KR",
) -> dict[str, object]:
    """Lint discovered dbt schema YAML and return a deterministic audit report."""
    if required_language != "ko-KR":
        report = _empty_report(
            "ERROR",
            [{"code": "UNSUPPORTED_LANGUAGE", "message": f"unsupported required language: {required_language}"}],
        )
        report["required_language"] = required_language
        return report

    paths, input_errors = _discover_files(schema_roots)
    if input_errors:
        return _empty_report("ERROR", input_errors)

    fallback_scope = Path(
        os.path.commonpath([path.parent.as_posix() for path in paths])
    ).resolve()

    selected = set(resources) if resources is not None else None
    if selected == set():
        selected = None
    file_reports: list[dict[str, object]] = []
    all_resources: list[dict[str, object]] = []
    all_descriptions: list[dict[str, object]] = []
    all_errors: list[dict[str, object]] = []
    discovered_names: set[str] = set()
    io_error = False

    for path in paths:
        path_string = path.as_posix()
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                raise ScanError(
                    f"file exceeds maximum size of {MAX_FILE_BYTES} bytes",
                    code="INPUT_LIMIT_EXCEEDED",
                )
            text = path.read_text(encoding="utf-8")
            root = _parse_yaml_subset(text)
            file_resources, descriptions, errors, discovered = _extract_resources(
                root, path_string, selected
            )
        except (OSError, UnicodeError) as error:
            io_error = True
            detail = {
                "code": "IO_ERROR",
                "file": path_string,
                "message": f"cannot read UTF-8 YAML: {error}",
            }
            all_errors.append(detail)
            file_reports.append(
                {"error_codes": ["IO_ERROR"], "path": path_string, "resource_names": [], "scan_status": "FAIL"}
            )
            continue
        except ScanError as error:
            detail: dict[str, object] = {
                "code": error.code,
                "file": path_string,
                "message": error.message,
            }
            if error.line is not None:
                detail["line"] = error.line
            if error.lines is not None:
                detail["lines"] = error.lines
            if error.key is not None:
                detail["key"] = error.key
            all_errors.append(detail)
            file_reports.append(
                {"error_codes": [error.code], "path": path_string, "resource_names": [], "scan_status": "FAIL"}
            )
            continue

        project_scope = _nearest_project_scope(path, fallback_scope)
        for resource in file_resources:
            resource["project_scope"] = project_scope
        discovered_names.update(discovered)
        all_resources.extend(file_resources)
        all_descriptions.extend(descriptions)
        all_errors.extend(errors)
        file_reports.append(
            {
                "error_codes": sorted({error["code"] for error in errors}),
                "path": path_string,
                "resource_names": [resource["name"] for resource in file_resources],
                "scan_status": "PASS",
            }
        )

    all_errors.extend(_cross_file_duplicate_errors(all_resources))

    if selected is not None:
        for missing in sorted(selected - discovered_names):
            all_errors.append(
                {
                    "code": "RESOURCE_NOT_FOUND",
                    "message": f"selected resource was not discovered: {missing}",
                    "resource_name": missing,
                }
            )

        for selector in sorted(selected & discovered_names):
            project_scopes = sorted(
                {
                    str(resource["project_scope"])
                    for resource in all_resources
                    if resource["name"] == selector
                }
            )
            if len(project_scopes) > 1:
                all_errors.append(
                    {
                        "code": "RESOURCE_SELECTOR_AMBIGUOUS",
                        "message": (
                            f"selected resource exists in multiple dbt projects: {selector}"
                        ),
                        "project_scopes": project_scopes,
                        "resource_name": selector,
                    }
                )

    all_errors.sort(key=_error_sort_key)
    resources_unaccounted = sum(
        error["code"] in {"MISSING_RESOURCE_NAME", "RESOURCE_NOT_FOUND"}
        for error in all_errors
    )
    descriptions_unaccounted = sum(
        error["code"]
        in {"MISSING_COLUMN_NAME", "MISSING_RESOURCE_NAME", "RESOURCE_NOT_FOUND"}
        for error in all_errors
    )
    descriptions_expected = len(all_descriptions) + descriptions_unaccounted
    descriptions_accounted = sum(bool(item["accounted"]) for item in all_descriptions)
    files_scanned = sum(item["scan_status"] == "PASS" for item in file_reports)
    resources_scanned = len(all_resources)
    resources_total = len(all_resources) + resources_unaccounted
    denominator = len(file_reports) + resources_total + descriptions_expected
    numerator = files_scanned + resources_scanned + descriptions_accounted
    coverage = round(100.0 * numerator / denominator, 2) if denominator else 0.0
    status = "ERROR" if io_error else ("FAIL" if all_errors else "PASS")
    report: dict[str, object] = {
        "descriptions": all_descriptions,
        "errors": all_errors,
        "files": file_reports,
        "required_language": required_language,
        "resources": all_resources,
        "status": status,
        "summary": {
            "coverage_percentage": coverage,
            "description_fields_accounted": descriptions_accounted,
            "description_fields_expected": descriptions_expected,
            "description_fields_present": sum(bool(item["present"]) for item in all_descriptions),
            "description_fields_unaccounted": descriptions_unaccounted,
            "error_count": len(all_errors),
            "files_scanned": files_scanned,
            "files_total": len(file_reports),
            "resources_scanned": resources_scanned,
            "resources_total": resources_total,
            "resources_unaccounted": resources_unaccounted,
        },
    }
    report.update(
        _proof_fields(
            status=status,
            errors=all_errors,
            files_complete=files_scanned == len(file_reports),
        )
    )
    return report


def render_report(report: dict[str, object]) -> str:
    return json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema-root", action="append", required=True, help="YAML file or directory")
    parser.add_argument("--resource", action="append", help="governed resource name")
    parser.add_argument("--require-language", required=True, help="required description language")
    parser.add_argument("--output", help="write JSON report to this existing-parent path")
    return parser


def _validate_output_path(
    output: Path,
    report: dict[str, object],
    schema_roots: Iterable[str | Path],
) -> tuple[Path | None, str | None]:
    requested = output.expanduser().absolute()
    if requested.is_symlink():
        return None, f"output symlinks are unsupported: {requested.as_posix()}"
    parent = requested.parent
    if not parent.exists() or not parent.is_dir():
        return None, f"output parent is not an existing directory: {parent.as_posix()}"
    if requested.exists() and not requested.is_file():
        return None, f"output path is not a regular file: {requested.as_posix()}"

    try:
        canonical_output = parent.resolve(strict=True) / requested.name
    except OSError as error:
        return None, f"cannot resolve output parent {parent.as_posix()}: {error}"
    input_paths = {
        Path(str(item["path"])).resolve(strict=False)
        for item in report.get("files", [])
        if isinstance(item, dict) and "path" in item
    }
    protected_directories: set[Path] = set()
    for root_value in schema_roots:
        raw_root = Path(root_value).expanduser().absolute()
        canonical_root = raw_root.resolve(strict=False)
        input_paths.add(canonical_root)
        if canonical_root.is_dir():
            protected_directories.add(canonical_root)
            try:
                requested.relative_to(raw_root)
            except ValueError:
                pass
            else:
                return None, f"output path is inside a schema root: {requested.as_posix()}"
            try:
                for candidate in canonical_root.rglob("*"):
                    resolved_candidate = candidate.resolve(strict=False)
                    if candidate.is_symlink():
                        if resolved_candidate.is_dir():
                            protected_directories.add(resolved_candidate)
                        else:
                            input_paths.add(resolved_candidate)
                    if candidate.is_file() and candidate.suffix.lower() in YAML_SUFFIXES:
                        input_paths.add(resolved_candidate)
            except OSError:
                pass
    for protected_directory in sorted(protected_directories, key=lambda path: path.as_posix()):
        try:
            canonical_output.relative_to(protected_directory)
        except ValueError:
            continue
        return None, f"output path is inside a schema root: {requested.as_posix()}"
    if canonical_output in input_paths:
        return None, f"output path collides with a discovered YAML input: {requested.as_posix()}"
    return canonical_output, None


def _atomic_write_text(path: Path, value: str) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _argument_parser().parse_args(argv)
    report = lint_schema_contracts(
        arguments.schema_root,
        resources=arguments.resource,
        required_language=arguments.require_language,
    )
    rendered = render_report(report)
    if arguments.output:
        output, validation_error = _validate_output_path(
            Path(arguments.output), report, arguments.schema_root
        )
        if validation_error is not None or output is None:
            print(f"cannot write output '{arguments.output}': {validation_error}", file=sys.stderr)
            return 2
        try:
            _atomic_write_text(output, rendered)
        except (OSError, UnicodeError) as error:
            print(f"cannot write output '{output}': {error}", file=sys.stderr)
            return 2
    else:
        write_utf8_stdout(rendered)
    return {"PASS": 0, "FAIL": 1, "ERROR": 2}[str(report["status"])]


if __name__ == "__main__":
    raise SystemExit(main())
