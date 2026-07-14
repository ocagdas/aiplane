from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import dump_yaml, parse_yaml
from .persistence import atomic_write_text

_GENERATED_CONFIG_CACHE: dict[tuple[Path, int, int], dict[str, Any]] = {}


class ModelCatalogStore:
    """Own curated/generated model-catalog paths, serialization, and cache invalidation."""

    def __init__(self, root: Path, generated_filename: str, generated_banner: str):
        self.root = root
        self.curated_path = root / "models.yaml"
        self.generated_path = root / generated_filename
        self.generated_banner = generated_banner

    def load_generated(self) -> dict[str, Any]:
        path = self.generated_path
        if not path.exists():
            return {}
        stat = path.stat()
        cache_key = (path.resolve(), stat.st_mtime_ns, stat.st_size)
        cached = _GENERATED_CONFIG_CACHE.get(cache_key)
        if cached is not None:
            return cached
        data = parse_yaml(path.read_text(encoding="utf-8"))
        parsed = data if isinstance(data, dict) else {}
        _GENERATED_CONFIG_CACHE.clear()
        _GENERATED_CONFIG_CACHE[cache_key] = parsed
        return parsed

    def write_curated(self, config: dict[str, Any]) -> Path:
        atomic_write_text(self.curated_path, dump_yaml(config))
        return self.curated_path

    def write_generated(self, config: dict[str, Any]) -> Path:
        atomic_write_text(self.generated_path, self.generated_banner + dump_yaml(config))
        _GENERATED_CONFIG_CACHE.clear()
        return self.generated_path
