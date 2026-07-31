from pathlib import Path


class AssetPaths:
    def __init__(self, root_dir: Path | None = None):
        self.root_dir = root_dir or Path.cwd()
        self.assets_dir = self.root_dir / "assets"
        self.video_clips_dir = self.assets_dir / "video_clips"
        self.fallback_image = self.assets_dir / "fallback.png"

        self.video_clips_dir.mkdir(parents=True, exist_ok=True)

    def scene_image_a(self, scene_id: int) -> Path:
        return self.video_clips_dir / f"scene_{scene_id}_a.png"

    def scene_image_b(self, scene_id: int) -> Path:
        return self.video_clips_dir / f"scene_{scene_id}_b.png"

    def file_ready(self, path: Path) -> bool:
        return path.exists() and path.stat().st_size > 0