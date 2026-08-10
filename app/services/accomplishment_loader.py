"""Loads the accomplishment/story bank (data/accomplishments.json).

Accomplishments are static, hand-curated data (not user-editable via the API),
so they are loaded straight from disk rather than stored in the database —
similar in spirit to how the README describes ``data/accomplishments.json``
as a "story bank" for narrative/report generation.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

from app.config import get_settings
from app.schemas.resume import AccomplishmentEntry

logger = logging.getLogger(__name__)


@lru_cache(maxsize=8)
def _load_from_path(path_str: str) -> tuple[AccomplishmentEntry, ...]:
    path = Path(path_str)
    if not path.exists():
        logger.warning("Accomplishments file not found at %s; returning empty list.", path)
        return ()
    raw = json.loads(path.read_text(encoding="utf-8"))
    return tuple(AccomplishmentEntry.model_validate(item) for item in raw)


def load_accomplishments(path: Path | None = None) -> list[AccomplishmentEntry]:
    """Load and cache accomplishments from disk.

    Uses ``Settings.accomplishments_file`` by default. Pass an explicit ``path``
    (e.g. in tests) to load a different file.
    """
    resolved = path if path is not None else get_settings().accomplishments_file
    return list(_load_from_path(str(resolved)))


def clear_accomplishments_cache() -> None:
    """Clear the cached accomplishment data — mainly useful for tests."""
    _load_from_path.cache_clear()
