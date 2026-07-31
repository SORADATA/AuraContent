from pathlib import Path


class AssetPaths:
    # On retire le paramètre par défaut pour forcer le développeur à préciser le dossier
    def __init__(self, root_dir: Path): 
        self.root_dir = root_dir
        self.assets_dir = self.root_dir / "assets"
        self.video_clips_dir = self.assets_dir / "video_clips"
        self.fallback_image = self.assets_dir / "fallback.png"

        self.video_clips_dir.mkdir(parents=True, exist_ok=True)