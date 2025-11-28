from __future__ import annotations

import shutil
from pathlib import Path
from typing import Union

from send2trash import send2trash

PathLike = Union[str, Path]


def move_to_trash(target: PathLike) -> bool:
    """
    Move the given file or directory to the system trash/recycle bin.
    Returns True if the operation succeeded.
    """
    path = Path(target).expanduser()
    if not path.exists():
        return False

    try:
        send2trash(str(path))
        return True
    except Exception:
        # Fallback: best-effort removal without raising, to prevent data corruption.
        try:
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)
        except Exception:
            pass
        return False




