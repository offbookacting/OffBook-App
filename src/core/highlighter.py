# core/highlighter.py
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Tuple, Optional

# We depend on the parsing structures to know where dialogue lives.
from core.nlp_processor import ScriptParse, blocks_for_character

# PyQt is optional. We keep Qt-specific helpers guarded.
try:
    from PyQt6.QtGui import QTextCharFormat, QColor
    from PyQt6.QtWidgets import QTextEdit
    _HAVE_QT = True
except Exception:
    _HAVE_QT = False


# ----------------------------
# Data types
# ----------------------------

@dataclass(frozen=True)
class HighlightSpan:
    """Inclusive line-span for a dialogue block."""
    start_line: int
    end_line: int  # inclusive


@dataclass(frozen=True)
class TextRange:
    """Flat character-range in a whole-document string."""
    start_pos: int  # inclusive
    end_pos: int    # exclusive


# ----------------------------
# Core computation (widget-agnostic)
# ----------------------------

def compute_line_offsets(lines: List[str]) -> List[int]:
    """
    Returns cumulative character offsets for each line’s start,
    assuming the final text is '\n'.join(lines).
    """
    offsets: List[int] = []
    cur = 0
    for ln in lines:
        offsets.append(cur)
        cur += len(ln) + 1  # +1 for the newline we’ll join with
    return offsets


def get_highlight_spans(parse: ScriptParse, character: str) -> List[HighlightSpan]:
    """
    Convert DialogueBlocks for a character into inclusive line spans.
    """
    spans: List[HighlightSpan] = []
    for b in blocks_for_character(parse, character):
        s = max(0, b.start_line)
        e = max(s, b.end_line)
        spans.append(HighlightSpan(start_line=s, end_line=e))
    # Optional: merge adjacent/overlapping spans
    return merge_spans(spans)


def merge_spans(spans: List[HighlightSpan]) -> List[HighlightSpan]:
    """
    Merge overlapping or immediately-adjacent line spans.
    """
    if not spans:
        return []
    spans_sorted = sorted(spans, key=lambda sp: (sp.start_line, sp.end_line))
    merged: List[HighlightSpan] = [spans_sorted[0]]
    for sp in spans_sorted[1:]:
        last = merged[-1]
        if sp.start_line <= last.end_line + 1:
            # overlap or adjacency -> extend
            merged[-1] = HighlightSpan(
                start_line=last.start_line,
                end_line=max(last.end_line, sp.end_line),
            )
        else:
            merged.append(sp)
    return merged


def spans_to_ranges(
    spans: List[HighlightSpan],
    line_offsets: List[int],
    lines: List[str],
) -> List[TextRange]:
    """
    Map line spans to concrete flat character ranges for '\n'.join(lines).
    """
    ranges: List[TextRange] = []
    n = len(lines)
    total_len = sum(len(l) for l in lines) + max(0, n - 1)
    for sp in spans:
        s = min(max(0, sp.start_line), n - 1) if n else 0
        e = min(max(0, sp.end_line), n - 1) if n else 0
        if not n:
            ranges.append(TextRange(0, 0))
            continue
        start_pos = line_offsets[s]
        # end position is end of e-th line content (no trailing newline)
        end_pos = line_offsets[e] + len(lines[e])
        start_pos = max(0, min(start_pos, total_len))
        end_pos = max(start_pos, min(end_pos, total_len))
        ranges.append(TextRange(start_pos, end_pos))
    return ranges


def ranges_for_character(parse: ScriptParse, character: str, lines: List[str]) -> Tuple[List[int], List[TextRange]]:
    """
    Convenience: compute line_offsets and ranges in one call.
    Returns (line_offsets, ranges).
    """
    spans = get_highlight_spans(parse, character)
    line_offsets = compute_line_offsets(lines)
    ranges = spans_to_ranges(spans, line_offsets, lines)
    return line_offsets, ranges


# ----------------------------
# Qt helpers (optional)
# ----------------------------

def qt_apply_highlights(
    editor: "QTextEdit",
    ranges: List[TextRange],
    background: str = "#FFF59D",
    font_weight: int = 600,
) -> None:
    """
    Apply character-format highlights to a QTextEdit for given ranges.
    Safe no-op if PyQt6 isn't present.
    """
    if not _HAVE_QT or editor is None:
        return

    # Clear existing formats in-document
    cur = editor.textCursor()
    cur.beginEditBlock()
    cur.select(cur.SelectionType.Document)
    editor.textCursor().mergeCharFormat(QTextCharFormat())
    cur.endEditBlock()

    fmt = QTextCharFormat()
    fmt.setBackground(QColor(background))
    if font_weight:
        fmt.setFontWeight(font_weight)

    doc = editor.document()
    cur = editor.textCursor()
    cur.beginEditBlock()
    for r in ranges:
        cur.setPosition(r.start_pos)
        cur.setPosition(r.end_pos, cur.MoveMode.KeepAnchor)
        cur.mergeCharFormat(fmt)
    cur.endEditBlock()


def qt_clear_highlights(editor: "QTextEdit") -> None:
    """
    Remove all custom formatting in the QTextEdit.
    """
    if not _HAVE_QT or editor is None:
        return
    cur = editor.textCursor()
    cur.beginEditBlock()
    cur.select(cur.SelectionType.Document)
    editor.textCursor().mergeCharFormat(QTextCharFormat())
    cur.endEditBlock()


# ----------------------------
# Non-GUI preview utility
# ----------------------------

def decorate_text_preview(text: str, ranges: List[TextRange],
                          open_tag: str = "[[", close_tag: str = "]]") -> str:
    """
    Returns a plain-text preview with markers around highlighted ranges.
    Useful for CLI debugging or tests.
    """
    if not ranges:
        return text
    # Insert markers back-to-front to preserve offsets
    out = list(text)
    for r in sorted(ranges, key=lambda x: x.start_pos, reverse=True):
        # bounds check
        start = max(0, min(r.start_pos, len(out)))
        end = max(start, min(r.end_pos, len(out)))
        out.insert(end, close_tag)
        out.insert(start, open_tag)
    return "".join(out)