import os
import subprocess
from modules.visuals.wan_video_generator import generate_animated_scene


class SceneAnimator:
    """
    Génère la scène animée via Wan 2.2 (personnage + décor + mouvement),
    rallonge la vidéo si besoin, fusionne l'audio, avec fallback FFmpeg
    (zoompan) si le Space échoue.
    """
    def __init__(self):
        self.base_dir = os.path.join("assets", "mimolune")
        self.temp_dir = os.path.join(self.base_dir, "temp")
        os.makedirs(self.temp_dir, exist_ok=True)

    def _get_video_duration(self, video_path):
        """Récupère la durée d'une vidéo via ffprobe."""
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path
        ]
        try:
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
            return float(result.stdout.strip())
        except Exception as e:
            print(f"    ⚠️ Impossible de lire la durée de {video_path} : {e}")
            return None

    def _extend_video_to_duration(self, scene_id, video_path, target_duration):
        """
        Boucle la vidéo (avec effet ping-pong pour éviter un saut brutal)
        jusqu'à atteindre au moins target_duration secondes.
        """
        video_duration = self._get_video_duration(video_path)
        if not video_duration or video_duration >= target_duration:
            return video_path

        loops_needed = int(target_duration // video_duration) + 1
        output_path = os.path.join(self.temp_dir, f"extended_{scene_id}.mp4")

        cmd = [
            "ffmpeg", "-y",
            "-stream_loop", str(loops_needed - 1),
            "-i", video_path,
            "-t", str(target_duration),
            "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
            "-an",
            output_path
        ]

        try:
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
            print(f"    🔁 Vidéo scène {scene_id} rallongée de {video_duration:.1f}s à {target_duration:.1f}s")
            return output_path
        except subprocess.CalledProcessError as e:
            print(f"    ⚠️ Échec rallongement scène {scene_id}, vidéo originale conservée : {e.stderr[-300:]}")
            return video_path

    def _fallback_static_clip(self, scene_id, image_path, audio_path, duration):
        output_path = os.path.join(self.temp_dir, f"animated_{scene_id}.mp4")
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", image_path,
            "-i", audio_path,
            "-filter_complex",
            "[0:v]scale=1080:1920,zoompan=z='min(zoom+0.001,1.1)':d=1[video_out]",
            "-map", "[video_out]",
            "-map", "1:a",
            "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-shortest", output_path
        ]
        try:
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
            return output_path
        except subprocess.CalledProcessError as e:
            print(f"❌ Erreur FFmpeg fallback (Code {e.returncode}) sur la scène {scene_id} :")
            print(e.stderr[-500:])
            return None

    def _mux_audio(self, scene_id, video_path, audio_path):
        """Remplace/ajoute la piste audio de la vidéo Wan 2.2 par l'audio Mimolune (voix/chant)."""
        output_path = os.path.join(self.temp_dir, f"final_{scene_id}.mp4")
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", audio_path,
            "-map", "0:v", "-map", "1:a",
            "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-shortest", output_path
        ]
        try:
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
            return output_path
        except subprocess.CalledProcessError as e:
            print(f"❌ Erreur mux audio scène {scene_id} (Code {e.returncode}) :")
            print(e.stderr[-500:])
            return video_path

    def animate_scene(self, scene):
        scene_id = scene["id"]
        image_path = scene.get("background_image")
        audio_path = scene.get("audio_path")
        duration = scene.get("duration", 5)
        prompt = scene.get(
            "scene_prompt",
            "Mimolune the lion cub sings and dances gently, "
            "cinematic motion, smooth animation for children"
        )

        print(f"🎬 Animation de la scène {scene_id}...")

        video_path = generate_animated_scene(image_path, prompt, duration=duration)

        if video_path:
            print(f"✨ Scène {scene_id} animée via Wan 2.2")
            video_path = self._extend_video_to_duration(scene_id, video_path, duration)
            video_path = self._mux_audio(scene_id, video_path, audio_path)
        else:
            print(f"   ↪️ Fallback zoompan pour la scène {scene_id}")
            video_path = self._fallback_static_clip(scene_id, image_path, audio_path, duration)

        scene["video_path"] = video_path
        return scene

    def animate_all_scenes(self, scenes):
        for scene in scenes:
            self.animate_scene(scene)
        return scenes