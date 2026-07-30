import os
from modules.ai_image import AIImageGenerator

FALLBACK_IMAGE = os.path.join(os.getcwd(), "assets", "fallback.png")


class AssetManager:
    def __init__(self):
        self.image_dir = os.path.join(os.getcwd(), "assets", "video_clips")
        os.makedirs(self.image_dir, exist_ok=True)
        self.generator = AIImageGenerator()

        self.global_visual_rules = (
            "Vertical 9:16 cinematic documentary frame, realistic lighting, strong central subject, "
            "clean composition, realistic textures, natural anatomy, no text, no logo, no watermark, "
            "no interface, no subtitles, space preserved at top and bottom for captions."
        )

    def _compose_prompt(self, base_prompt, visual_identity=None, variant="a"):
        identity_block = f"{visual_identity}. " if visual_identity else ""

        if variant == "a":
            shot_block = (
                "Establishing shot, wider composition, clear environment context, "
                "subject readable instantly, stable framing."
            )
        else:
            shot_block = (
                "Closer cinematic shot, tighter framing, more emotional or investigative detail, "
                "same subject and same scene continuity."
            )

        return f"{identity_block}{base_prompt}. {shot_block} {self.global_visual_rules}"

    def _file_ready(self, path):
        return os.path.exists(path) and os.path.getsize(path) > 0

    def _generate_with_retry(self, prompt, output_path, visual_identity=None, retries=2):
        for attempt in range(1, retries + 1):
            try:
                ok = self.generator.generate_image(
                    prompt,
                    output_path,
                    visual_identity=visual_identity
                )
                if ok and self._file_ready(output_path):
                    return True
                print(f"      Tentative {attempt}/{retries} echouee pour {os.path.basename(output_path)}")
            except Exception as e:
                print(f"      Erreur tentative {attempt}/{retries} : {e}")

        return False

    def get_videos(self, script_data, visual_identity=None):
        """
        Genere 2 images IA coherentes (a/b) par scene.
        - image A : plan plus large / etablissant
        - image B : plan plus serre / detail narratif
        Si echec, fallback intelligent sur l'autre image ou sur une image locale.
        Retourne une liste de dicts {"a": path, "b": path} alignee avec script_data.
        """
        pairs = []

        for scene in script_data:
            scene_id = scene["id"]

            path_a = os.path.join(self.image_dir, f"scene_{scene_id}_a.png")
            path_b = os.path.join(self.image_dir, f"scene_{scene_id}_b.png")

            print(f"Scene {scene_id} - generation des visuels IA...")

            base_prompt = scene["image_prompt"].strip()
            prompt_a = self._compose_prompt(base_prompt, visual_identity=visual_identity, variant="a")
            prompt_b = self._compose_prompt(base_prompt, visual_identity=visual_identity, variant="b")

            ok_a = self._file_ready(path_a) or self._generate_with_retry(
                prompt_a, path_a, visual_identity=visual_identity, retries=2
            )
            ok_b = self._file_ready(path_b) or self._generate_with_retry(
                prompt_b, path_b, visual_identity=visual_identity, retries=2
            )

            if ok_a and ok_b:
                pairs.append({"a": path_a, "b": path_b})
            elif ok_a:
                print(f"    Scene {scene_id}: visual_2 a echoue, reutilisation de visual_1")
                pairs.append({"a": path_a, "b": path_a})
            elif ok_b:
                print(f"    Scene {scene_id}: visual_1 a echoue, reutilisation de visual_2")
                pairs.append({"a": path_b, "b": path_b})
            else:
                print(f"    Scene {scene_id}: aucune image generee, utilisation du fallback")
                if os.path.exists(FALLBACK_IMAGE):
                    pairs.append({"a": FALLBACK_IMAGE, "b": FALLBACK_IMAGE})
                else:
                    print(f"    Scene {scene_id}: fallback introuvable, scene ignoree")
                    pairs.append(None)

        return pairs
