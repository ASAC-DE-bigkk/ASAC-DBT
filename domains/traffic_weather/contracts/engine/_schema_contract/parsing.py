"""Internal _schema_contract parsing responsibility."""

from __future__ import annotations

import re

from .lexing import (
    _find_implicit_flow_mapping_colon,
    _find_mapping_colon,
    _find_plain_scalar_mapping_colon,
    _flow_bounds,
    _split_flow_items,
    _tokenize,
)

from .types import (
    BLOCK_SCALAR_RE,
    MAX_SCALAR_LENGTH,
    MapEntry,
    Node,
    ScanError,
    Token,
)


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
            raise ScanError(
                "malformed double-quoted scalar: trailing backslash", line=line
            )
        escape = value[index + 1]
        if escape in {"0", "a", "b", "v", "f", "e"}:
            raise ScanError(
                "double-quoted escape decodes to a forbidden control", line=line
            )
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
            raise ScanError(
                "double-quoted escape is not a Unicode scalar value", line=line
            )
        if (
            codepoint < 0x20
            or codepoint == 0x7F
            or (0x80 <= codepoint <= 0x9F and codepoint != 0x85)
        ):
            raise ScanError(
                "double-quoted escape decodes to a forbidden control", line=line
            )
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
        raise ScanError(
            "reserved YAML indicator cannot start a plain scalar", line=line
        )
    if value[:1] in {"?", "-", ":"} and (len(value) == 1 or value[1].isspace()):
        raise ScanError(
            "reserved YAML indicator cannot start a plain scalar", line=line
        )
    if _find_plain_scalar_mapping_colon(value) is not None:
        raise ScanError(
            "plain scalar contains an extra YAML mapping separator", line=line
        )
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
                raise ScanError(
                    "implicit mappings in flow sequences are unsupported", line=line
                )
            if item == "-" or item.startswith("- "):
                raise ScanError(
                    "implicit sequences in flow sequences are unsupported", line=line
                )
        return Node(
            kind="seq",
            line=line,
            sequence=[
                Node(kind="scalar", line=line, value=_decode_scalar(item, line))
                for item in items
            ],
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
            raise ScanError(
                "implicit mappings in flow-map values are unsupported", line=line
            )
        if raw_value == "-" or raw_value.startswith("- "):
            raise ScanError(
                "implicit sequences in flow-map values are unsupported", line=line
            )
        if key in seen:
            raise ScanError(
                f"duplicate mapping key '{key}'",
                code="DUPLICATE_MAPPING_KEY",
                lines=[seen[key], line],
                key=key,
            )
        seen[key] = line
        node.mapping.append(
            MapEntry(
                key=key,
                line=line,
                value=Node(
                    kind="scalar", line=line, value=_decode_scalar(raw_value, line)
                ),
            )
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
            raise ScanError(
                "mapping and sequence entries share one indentation", line=token.line
            )
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
                raise ScanError(
                    "scalar mapping value has nested indentation",
                    line=tokens[index].line,
                )
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
                raise ScanError(
                    "scalar sequence item has nested indentation",
                    line=tokens[index].line,
                )
        else:
            raise ScanError(
                "mapping and sequence entries share one indentation", line=token.line
            )
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
        raise ScanError(
            "scanner did not account for every structural line", line=tokens[index].line
        )
    if root.kind != "map":
        raise ScanError("schema root must be a block mapping", line=root.line)
    return root
