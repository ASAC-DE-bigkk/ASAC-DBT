"""Internal _schema_contract types responsibility."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

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
