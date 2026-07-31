from pathlib import Path

from modules.assets.asset_paths import AssetPaths
from modules.visuals.scene_image_service import SceneImageService


class AssetManager:
    def __init__(
        self,
        paths: AssetPaths | None = None,
        image_service: SceneImageService | None = None,
    ):
        self.paths = paths or AssetPaths()
        self.image_service = image_service or SceneImageService()

    def get_videos(self, script_data, visual_identity=None):
        """
        Génère 2 images IA cohérentes (a/b) par scène.
        - image A : plan plus large / établissant
        - image B : plan plus serré / détail narratif
        Si échec, fallback intelligent sur l'autre image ou sur une image locale.
        Retourne une liste de dicts {"a": path, "b": path} alignée avec script_data.
        """
        pairs = []

        for scene in script_data:
            scene_id = scene["id"]

            path_a = self.paths.scene_image_a(scene_id)
            path_b = self.paths.scene_image_b(scene_id)

            print(f"Scene {scene_id} - génération des visuels IA...")

            base_prompt = scene["image_prompt"].strip()
            prompt_a = self.image_service.compose_prompt(
                base_prompt,
                visual_identity=visual_identity,
                variant="a",
            )
            prompt_b = self.image_service.compose_prompt(
                base_prompt,
                visual_identity=visual_identity,
                variant="b",
            )

            ok_a = self.paths.file_ready(path_a) or self.image_service.generate_with_retry(
                prompt_a,
                path_a,
                visual_identity=visual_identity,
                retries=2,
            )
            ok_b = self.paths.file_ready(path_b) or self.image_service.generate_with_retry(
                prompt_b,
                path_b,
                visual_identity=visual_identity,
                retries=2,
            )

            if ok_a and ok_b:
                pairs.append({"a": str(path_a), "b": str(path_b)})
            elif ok_a:
                print(f"    Scene {scene_id}: visual_2 a échoué, réutilisation de visual_1")
                pairs.append({"a": str(path_a), "b": str(path_a)})
            elif ok_b:
                print(f"    Scene {scene_id}: visual_1 a échoué, réutilisation de visual_2")
                pairs.append({"a": str(path_b), "b": str(path_b)})
            else:
                print(f"    Scene {scene_id}: aucune image générée, utilisation du fallback")
                fallback = self.paths.fallback_image
                if fallback.exists():
                    pairs.append({"a": str(fallback), "b": str(fallback)})
                else:
                    print(f"    Scene {scene_id}: fallback introuvable, scène ignorée")
                    pairs.append(None)

        return pairs