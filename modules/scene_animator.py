import os
import subprocess
from constants_mimolune import POSES, MOUTHS
from modules.kids_tts import KidsAudioEngine


class SceneAnimator:
    """
    Assemble le fond, le corps du personnage et anime la bouche
    en rythme avec l'audio en utilisant FFmpeg.
    """
    def __init__(self):
        self.base_dir = os.path.join("assets", "mimolune")
        self.temp_dir = os.path.join(self.base_dir, "temp")
        self.char_dir = os.path.join(self.base_dir, "characters")
        os.makedirs(self.temp_dir, exist_ok=True)

    def _create_mouth_sequence(self, scene_id, speaker, envelope, chunk_ms):
        """Crée un fichier texte concat pour FFmpeg avec les formes de bouche."""
        sequence_path = os.path.join(self.temp_dir, f"mouth_seq_{scene_id}.txt")
        chunk_sec = chunk_ms / 1000.0

        with open(sequence_path, "w", encoding="utf-8") as f:
            for val in envelope:
                shape = KidsAudioEngine.mouth_shape_for_value(val)
                img_path = os.path.join(self.char_dir, speaker, f"mouth_{shape}.png")
                
                if not os.path.exists(img_path):
                    img_path = os.path.join(self.char_dir, "default_mouth.png")
                
                f.write(f"file '{os.path.abspath(img_path)}'\n")
                f.write(f"duration {chunk_sec}\n")
            
            if envelope:
                last_shape = KidsAudioEngine.mouth_shape_for_value(envelope[-1])
                last_path = os.path.join(self.char_dir, speaker, f"mouth_{last_shape}.png")
                f.write(f"file '{os.path.abspath(last_path)}'\n")

        return sequence_path

    def animate_scene(self, scene):
        scene_id = scene["id"]
        speaker = scene.get("speaker", "mimolune")
        action = scene.get("action", "repos")
        audio_path = scene.get("audio_path")
        envelope = scene.get("mouth_envelope", [])
        chunk_ms = scene.get("mouth_chunk_ms", 120)

        print(f"🎬 Animation de la scène {scene_id} ({speaker} - action: {action})...")

        bg_path = scene.get("background_image") 
        body_path = os.path.join(self.char_dir, speaker, f"pose_{action}.png")
        mouth_seq = self._create_mouth_sequence(scene_id, speaker, envelope, chunk_ms)
        output_path = os.path.join(self.temp_dir, f"animated_{scene_id}.mp4")

        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", bg_path,
            "-loop", "1", "-i", body_path,
            "-f", "concat", "-safe", "0", "-i", mouth_seq,
            "-i", audio_path,
            "-filter_complex",
            "[0:v]scale=1080:1920,zoompan=z='min(zoom+0.001,1.1)':d=1[bg];"
            "[bg][1:v]overlay=(W-w)/2:(H-h)/2+200:shortest=1[with_body];"
            "[with_body][2:v]overlay=(W-w)/2:(H-h)/2+200[video_out]",
            "-map", "[video_out]",
            "-map", "3:a",
            "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-shortest", output_path
        ]

        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            scene["video_path"] = output_path
            return scene
        except Exception as e:
            print(f"❌ Erreur FFmpeg lors de l'animation de la scène {scene_id} : {e}")
            return scene

    def animate_all_scenes(self, scenes):
        for scene in scenes:
            self.animate_scene(scene)
        return scenes
