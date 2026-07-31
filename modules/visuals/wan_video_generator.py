import os
import time
from pathlib import Path

from gradio_client import Client


class WanVideoGenerator:
    def __init__(self, hf_token=None):
        self.hf_token = hf_token or os.getenv("HF_TOKEN")
        self.space_candidates = [
            "zerogpu-aoti/wan2-2-fp8da-aoti-faster",
            "r3gm/wan2-2-fp8da-aoti-preview",
            "cinderholm/wan2-2-i2v-v3",
        ]

    def _build_client(self, space_name):
        if self.hf_token:
            try:
                return Client(space_name, token=self.hf_token)
            except TypeError:
                pass

        try:
            return Client(space_name)
        except TypeError:
            return Client(space_name)

    def _generate_with_space(self, space_name, scene_prompt, image_path=None):
        client = self._build_client(space_name)

        if image_path:
            result = client.predict(
                image=image_path,
                prompt=scene_prompt,
                api_name="/predict"
            )
        else:
            result = client.predict(
                prompt=scene_prompt,
                api_name="/predict"
            )

        return result

    def generate_clip(self, scene_prompt, image_path=None):
        last_error = None

        for space_name in self.space_candidates:
            try:
                print(f"   🔁 Tentative Wan 2.2 via {space_name}...")
                result = self._generate_with_space(
                    space_name=space_name,
                    scene_prompt=scene_prompt,
                    image_path=image_path
                )
                print(f"   ✅ Wan 2.2 OK via {space_name}")
                return result
            except Exception as e:
                print(f"   ⚠️ {space_name} indisponible ({e}), essai suivant")
                last_error = e
                continue

        raise RuntimeError(f"Tous les Spaces Wan 2.2 sont indisponibles: {last_error}")

    @staticmethod
    def ensure_output_dir(path):
        Path(path).mkdir(parents=True, exist_ok=True)
        return path
