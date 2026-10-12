"""Split filing text into overlapping chunks, remembering which Part/Item each came from."""
import re
from dataclasses import dataclass
from typing import Optional

PART_RE = re.compile(r"^part\s+(i{1,3}|iv)\.?$", re.IGNORECASE)
ITEM_RE = re.compile(r"^item\s+(\d+[a-c]?)\.?(\s|$)", re.IGNORECASE)


@dataclass(frozen=True)
class Chunk:
    index: int
    section: Optional[str]
    text: str


def _split_long(line: str, limit: int) -> list[str]:
    pieces = []
    while len(line) > limit:
        cut = line.rfind(" ", 0, limit)
        cut = cut if cut > limit // 2 else limit
        pieces.append(line[:cut].strip())
        line = line[cut:].strip()
    if line:
        pieces.append(line)
    return pieces


def chunk_text(text: str, target: int = 1200, overlap: int = 150) -> list[Chunk]:
    part: Optional[str] = None
    item: Optional[str] = None
    units: list[tuple[Optional[str], str]] = []  # (section label, line)

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if m := PART_RE.match(line):
            part, item = f"Part {m.group(1).upper()}", None
        elif m := ITEM_RE.match(line):
            item = f"Item {m.group(1).upper()}"
        label = ", ".join(x for x in (part, item) if x) or None
        for piece in _split_long(line, target):
            units.append((label, piece))

    chunks: list[Chunk] = []
    current: list[tuple[Optional[str], str]] = []
    size = 0
    fresh = 0  # lines added since the last emit, excluding the carried-over overlap

    def emit() -> None:
        weight: dict[Optional[str], int] = {}
        for label, line in current:
            weight[label] = weight.get(label, 0) + len(line)
        section = max(weight, key=weight.get)  # the section holding most of this chunk's text
        chunks.append(Chunk(len(chunks), section, "\n".join(u[1] for u in current)))

    for unit in units:
        if current and size + len(unit[1]) + 1 > target:
            emit()
            tail, kept = [], 0
            for u in reversed(current):
                if kept + len(u[1]) > overlap:
                    break
                tail.insert(0, u)
                kept += len(u[1]) + 1
            if kept + len(unit[1]) + 1 > target:
                tail, kept = [], 0  # no room for overlap next to a long line
            current, size, fresh = tail, kept, 0
        current.append(unit)
        size += len(unit[1]) + 1
        fresh += 1
    if fresh:
        emit()
    return chunks
