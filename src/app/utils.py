# app/utils.py
from __future__ import annotations
import re
import shutil
import subprocess
from pathlib import Path
from typing import Iterable, Tuple, List

# Reuse core utilities where appropriate
try:
    from core.highlighter import compute_line_offsets, spans_to_ranges, HighlightSpan, TextRange  # noqa: F401
except Exception:
    # Soft fallback stubs; real app will import from core.highlighter
    def compute_line_offsets(lines: List[str]) -> List[int]:
        offs, cur = [], 0
        for ln in lines:
            offs.append(cur); cur += len(ln) + 1
        return offs
    class HighlightSpan:  # type: ignore
        def __init__(self, start_line: int, end_line: int): ...
    class TextRange:  # type: ignore
        def __init__(self, start_pos: int, end_pos: int): ...
    def spans_to_ranges(spans, line_offsets, lines): return []  # type: ignore


# ---------- Paths / Files ----------

def ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p

def validate_pdf(path: str | Path) -> Path:
    p = Path(path).expanduser()
    if not p.exists() or p.suffix.lower() != ".pdf":
        raise FileNotFoundError(f"PDF not found or invalid: {p}")
    return p

def human_size(nbytes: int) -> str:
    if nbytes < 1024: return f"{nbytes} B"
    units = ["KB", "MB", "GB", "TB"]
    size = float(nbytes)
    for u in units:
        size /= 1024.0
        if size < 1024.0:
            return f"{size:.1f} {u}"
    return f"{size:.1f} PB"

def atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding=encoding)
    tmp.replace(path)

def copy_into(dst_dir: Path, src_file: Path, dst_name: str | None = None) -> Path:
    ensure_dir(dst_dir)
    target = dst_dir / (dst_name or src_file.name)
    if str(src_file.resolve()) != str(target.resolve()):
        shutil.copy2(str(src_file), str(target))
    return target

# ---------- Names / Strings ----------

_INVALID_CHARS = re.compile(r"[^A-Za-z0-9._ -]+")

def slugify_project_name(name: str, max_len: int = 64) -> str:
    base = _INVALID_CHARS.sub("", name).strip()
    base = re.sub(r"\s+", "_", base)
    return (base or "Project")[:max_len]

def unique_name(preferred: str, existing: Iterable[str]) -> str:
    base = preferred
    n = 1
    s = set(existing)
    while preferred in s:
        n += 1
        preferred = f"{base}_{n}"
    return preferred

# ---------- macOS helpers ----------

def reveal_in_finder(path: str | Path) -> None:
    """Reveal a file or folder in Finder."""
    p = str(Path(path).expanduser())
    try:
        subprocess.run(["open", "-R", p], check=False)
    except Exception:
        pass

def open_with_default_app(path: str | Path) -> None:
    """Open with the default registered app (macOS)."""
    p = str(Path(path).expanduser())
    try:
        subprocess.run(["open", p], check=False)
    except Exception:
        pass

# ---------- Text mapping utilities (thin wrappers around core.highlighter) ----------

def map_line_spans_to_ranges(
    lines: List[str],
    spans: List[HighlightSpan],
) -> Tuple[List[int], List[TextRange]]:
    """Compute line offsets and map spans to flat character ranges."""
    offsets = compute_line_offsets(lines)
    ranges = spans_to_ranges(spans, offsets, lines)
    return offsets, ranges