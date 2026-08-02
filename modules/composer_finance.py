import os
import random
import time
import urllib.parse
import requests
import ffmpeg

try:
    from modules.kinetic_typography_v2 import KineticTypographyEngineV2
    KINETIC_MODULE_AVAILABLE = True
except ImportError:
    print("⚠️ kinetic_typography_v2.py introuvable. Fallback sur Pexels par défaut.")
    KINETIC_MODULE_AVAILABLE = False


class Composer:
    def __init__(self):
        self.temp_dir = os.path.join(os.getcwd(), "assets", "temp")
        self.final_dir = os.path.join(os.getcwd(), "assets", "final")
        self.music_dir = os.path.join(os.getcwd(), "assets", "music")

        os.makedirs(self.temp_dir, exist_ok=True)
        os.makedirs(self.final_dir, exist_ok=True)
        os.makedirs(self.music_dir, exist_ok=True)

        self.transitions = ["fade", "diagbr", "diagtl"]
        self.bg_music_path = os.path.join(self.music_dir, "bg_track_finance.mp3")

        self.video_width = 1080
        self.video_height = 1920
        self.fps = 30

        self.voice_gain = 1.15
        self.music_gain = 0.12
        self.music_fade_duration = 1.5
        self.transition_duration = 0.45

        self.subtitle_style = (
            "FontName=Montserrat,"
            "FontSize=22,"
            "PrimaryColour=&H00FFFFFF,"
            "OutlineColour=&H00000000,"
            "BackColour=&H99000000,"
            "BorderStyle=3,"
            "Outline=2.5,"
            "Shadow=0,"
            "Alignment=2,"
            "MarginV=130"
        )

        # --- Instanciation sécurisée du moteur kinetic typography ---
        # KineticTypographyEngineV2 peut lever FileNotFoundError si les
        # polices sont manquantes. On ne veut JAMAIS que ça fasse planter
        # tout le Composer : on bascule proprement sur les fallbacks
        # (Pexels / Pollinations) si le moteur n'est pas disponible.
        self.kinetic_engine = None
        self.kinetic_available = False

        if KINETIC_MODULE_AVAILABLE:
            try:
                self.kinetic_engine = KineticTypographyEngineV2(
                    width=self.video_width,
                    height=self.video_height,
                    fps=self.fps
                )
                self.kinetic_available = True
            except (FileNotFoundError, OSError) as e:
                print(f"⚠️ Kinetic engine indisponible ({e}). Fallback sur Pexels/Pollinations.")
                self.kinetic_available = False

    def get_duration(self, filepath):
        try:
            probe = ffmpeg.probe(filepath)
            return float(probe["format"]["duration"])
        except Exception:
            return 0.0

    @staticmethod
    def _escape_ffmpeg_path(path):
        """Escape a filesystem path for use inside an ffmpeg filter option
        (e.g. subtitles=filename=...). Colons and backslashes must be
        escaped or the filtergraph parser breaks — this bites hard on
        Windows paths (C:\\...) and any path containing ':'."""
        return path.replace("\\", "\\\\").replace(":", "\\:")

    def _generate_pollinations_video(self, scene_id, prompt, duration):
        if not prompt:
            return None

        image_path = os.path.join(self.temp_dir, f"pollinations_{scene_id}.jpg")
        video_path = os.path.join(self.temp_dir, f"pollinations_{scene_id}.mp4")

        encoded_prompt = urllib.parse.quote(prompt)
        seed = random.randint(1, 999999)
        url = (
            f"https://image.pollinations.ai/prompt/{encoded_prompt}"
            f"?width={self.video_width}&height={self.video_height}&model=flux&nologo=true&seed={seed}"
        )

        try:
            response = requests.get(url, timeout=30)
            if response.status_code == 200:
                with open(image_path, "wb") as f:
                    f.write(response.content)
            else:
                return None
        except Exception as e:
            print(f"⚠️ Pollinations erreur: {e}")
            return None

        try:
            zoom_frames = int(duration * self.fps)
            (
                ffmpeg.input(image_path, loop=1, t=duration)
                .filter("scale", self.video_width * 2, self.video_height * 2)
                .filter(
                    "zoompan",
                    z="min(zoom+0.0008,1.15)",
                    d=zoom_frames,
                    x="iw/2-(iw/zoom/2)",
                    y="ih/2-(ih/zoom/2)",
                    s=f"{self.video_width}x{self.video_height}",
                    fps=self.fps,
                )
                .output(
                    video_path,
                    vcodec="libx264",
                    pix_fmt="yuv420p",
                    crf=18,
                    preset="medium",
                    t=duration
                )
                .run(overwrite_output=True, quiet=True)
            )
            return video_path
        except Exception:
            return None

    def _get_visual_for_scene(self, scene, default_pexels_path, total_duration):
        scene_id = scene["id"]
        role = scene.get("role", "example")
        prompt = scene.get("image_prompt", "")

        if role in {"definition", "mechanism", "summary"} and self.kinetic_available:
            print(f"    🔤 Scène {scene_id} ({role}) : Kinetic Typography")
            kinetic_out = os.path.join(self.temp_dir, f"kinetic_{scene_id}.mp4")
            result = self.kinetic_engine.generate(scene, total_duration, kinetic_out)
            if result and os.path.exists(result):
                return result, "kinetic"

        if role in {"misconception", "analogy"} and prompt:
            print(f"    🎨 Scène {scene_id} ({role}) : Génération image Pollinations IA + Zoom")
            pollinations_out = self._generate_pollinations_video(scene_id, prompt, total_duration)
            if pollinations_out and os.path.exists(pollinations_out):
                return pollinations_out, "image_ai"

        if default_pexels_path and os.path.exists(default_pexels_path):
            print(f"    🎬 Scène {scene_id} ({role}) : Vidéo Pexels dynamique")
            return default_pexels_path, "video"

        if self.kinetic_available:
            print(f"    🔤 Scène {scene_id} ({role}) : Fallback Kinetic")
            kinetic_out = os.path.join(self.temp_dir, f"kinetic_fallback_{scene_id}.mp4")
            result = self.kinetic_engine.generate(scene, total_duration, kinetic_out)
            if result and os.path.exists(result):
                return result, "kinetic"

        return None, "none"

    def process_scene(self, scene, video_path):
        scene_id = scene["id"]
        audio_path = scene["audio_path"]
        total_duration = float(scene["duration"])
        output_path = os.path.join(self.temp_dir, f"scene_{scene_id}.mp4")

        try:
            final_video_path, visual_type = self._get_visual_for_scene(scene, video_path, total_duration)

            if not final_video_path or not os.path.exists(final_video_path):
                print(f"❌ Impossible de trouver un visuel pour la scène {scene_id}")
                return None

            print(f"    ⚙️ Assemblage FFmpeg Scène {scene_id} (Type: {visual_type})")

            input_audio = ffmpeg.input(audio_path)
            input_video = ffmpeg.input(final_video_path, stream_loop=-1)

            video_stream = (
                input_video.video
                .trim(duration=total_duration)
                .setpts("PTS-STARTPTS")
                .filter("scale", "1080", "1920", force_original_aspect_ratio="increase")
                .filter("crop", "1080", "1920")
            )

            srt_path = scene.get("srt_path")
            if srt_path and os.path.exists(srt_path):
                video_stream = video_stream.filter(
                    "subtitles",
                    filename=self._escape_ffmpeg_path(srt_path),
                    force_style=self.subtitle_style
                )

            runner = ffmpeg.output(
                video_stream,
                input_audio,
                output_path,
                vcodec="libx264",
                acodec="aac",
                pix_fmt="yuv420p",
                r=self.fps,
                crf=18,
                preset="medium",
                shortest=None
            )

            runner.run(overwrite_output=True, quiet=True)
            return output_path

        except ffmpeg.Error as e:
            print(f"❌ Render Fail Scene {scene_id}: {e.stderr.decode('utf8') if e.stderr else str(e)}")
            return None

    def render_all_scenes(self, script_data, video_paths):
        rendered_paths = []
        for i, scene in enumerate(script_data):
            current_video = video_paths[i] if i < len(video_paths) else None
            output_path = self.process_scene(scene, current_video)
            if output_path:
                rendered_paths.append(output_path)
        return rendered_paths

    def _merge_two_clips(self, clip_a, clip_b, output_path, trans_dur=None):
        trans_dur = trans_dur or self.transition_duration
        dur_a = self.get_duration(clip_a)
        offset = max(dur_a - trans_dur, 0)
        effect = random.choice(self.transitions)

        input_a = ffmpeg.input(clip_a)
        input_b = ffmpeg.input(clip_b)

        v_stream = ffmpeg.filter(
            [input_a.video, input_b.video],
            "xfade",
            transition=effect,
            duration=trans_dur,
            offset=offset
        )

        a_stream = ffmpeg.filter(
            [input_a.audio, input_b.audio],
            "acrossfade",
            d=trans_dur
        )

        runner = ffmpeg.output(
            v_stream,
            a_stream,
            output_path,
            vcodec="libx264",
            acodec="aac",
            pix_fmt="yuv420p",
            crf=18,
            preset="medium"
        )
        runner.run(overwrite_output=True, quiet=True)
        return effect, offset

    def _normalize_audio_track(self, input_video_path, output_video_path):
        try:
            src = ffmpeg.input(input_video_path)
            normalized_audio = src.audio.filter("loudnorm", I=-16, TP=-1.5, LRA=11)
            runner = ffmpeg.output(
                src.video,
                normalized_audio,
                output_video_path,
                vcodec="copy",
                acodec="aac",
                audio_bitrate="192k",
                movflags="faststart"
            )
            runner.run(overwrite_output=True, quiet=True)
            return True
        except ffmpeg.Error as e:
            error_log = e.stderr.decode("utf8") if e.stderr else str(e)
            print(f"⚠️ Loudnorm failed: {error_log}")
            return False

    def _mix_background_music(self, stitched_path, output_path):
        try:
            video_duration = self.get_duration(stitched_path)
            fade_start = max(video_duration - self.music_fade_duration, 0)

            voice = ffmpeg.input(stitched_path)
            music = ffmpeg.input(self.bg_music_path, stream_loop=-1)

            voice_audio_base = (
                voice.audio
                .filter("aformat", sample_fmts="fltp", sample_rates=48000, channel_layouts="stereo")
                .filter("volume", self.voice_gain)
                .filter("atrim", duration=video_duration)
                .filter("asetpts", "PTS-STARTPTS")
            )

            music_audio_base = (
                music.audio
                .filter("aformat", sample_fmts="fltp", sample_rates=48000, channel_layouts="stereo")
                .filter("volume", self.music_gain)
                .filter("atrim", duration=video_duration)
                .filter("asetpts", "PTS-STARTPTS")
                .filter("afade", type="out", start_time=fade_start, duration=self.music_fade_duration)
            )

            voice_split = voice_audio_base.filter_multi_output("asplit", 2)
            voice_for_sidechain = voice_split[0]
            voice_for_mix = voice_split[1]

            music_split = music_audio_base.filter_multi_output("asplit", 2)
            music_for_sidechain = music_split[0]
            music_for_mix = music_split[1]

            ducked_music = ffmpeg.filter(
                [music_for_sidechain, voice_for_sidechain],
                "sidechaincompress",
                threshold=0.03,
                ratio=10,
                attack=20,
                release=250,
                makeup=1
            )

            mixed_audio = (
                ffmpeg
                .filter(
                    [voice_for_mix, ducked_music],
                    "amix",
                    inputs=2,
                    duration="first",
                    dropout_transition=2,
                    normalize=0
                )
                .filter("loudnorm", I=-16, TP=-1.5, LRA=11)
            )

            final_runner = ffmpeg.output(
                voice.video,
                mixed_audio,
                output_path,
                vcodec="libx264",
                acodec="aac",
                audio_bitrate="192k",
                pix_fmt="yuv420p",
                movflags="faststart",
                preset="medium"
            )
            final_runner.run(overwrite_output=True, quiet=False)
            print(f"✅ FINAL VIDEO SAVED (with music): {output_path}")
            return True

        except ffmpeg.Error as e:
            error_log = e.stderr.decode("utf8") if e.stderr else str(e)
            print(f"⚠️ Music mix failed, falling back to no-music version: {error_log}")
            return False

    def _cleanup_scene_temp_files(self, video_paths):
        """Remove the per-scene intermediate .mp4 files once the final
        video has been stitched, so temp_dir doesn't accumulate disk
        usage across runs."""
        for path in video_paths:
            if path and os.path.exists(path) and os.path.dirname(path) == self.temp_dir:
                try:
                    os.remove(path)
                except Exception:
                    pass

    def concatenate_with_transitions(self, video_paths, output_filename="final_short.mp4"):
        print("🎬 Stitching final video (cascade mode)...")
        output_path = os.path.join(self.final_dir, output_filename)

        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except Exception:
                pass

        if not video_paths:
            return None

        if len(video_paths) == 1:
            stitched_path = video_paths[0]
        else:
            courant = video_paths[0]
            for i in range(1, len(video_paths)):
                suivant = video_paths[i]
                merge_output = os.path.join(self.temp_dir, f"merge_step_{i}.mp4")
                try:
                    effect, offset = self._merge_two_clips(courant, suivant, merge_output)
                    print(f"    ✨ Transition {i}: '{effect}' at {offset:.2f}s")
                except ffmpeg.Error as e:
                    print(f"❌ Stitching Error at step {i}: {e.stderr.decode('utf8') if e.stderr else str(e)}")
                    return None

                if i > 1 and courant.startswith(os.path.join(self.temp_dir, "merge_step_")):
                    try:
                        os.remove(courant)
                    except Exception:
                        pass

                courant = merge_output
            stitched_path = courant

        if os.path.exists(self.bg_music_path):
            print("🎵 Mixing background music with ducking...")
            success = self._mix_background_music(stitched_path, output_path)
            if not success:
                normalized_fallback = os.path.join(self.temp_dir, "normalized_no_music.mp4")
                ok = self._normalize_audio_track(stitched_path, normalized_fallback)
                if ok and os.path.exists(normalized_fallback):
                    os.replace(normalized_fallback, output_path)
                else:
                    os.replace(stitched_path, output_path)
        else:
            print("⚠️ Aucune musique de fond trouvée, export avec voix normalisée.")
            normalized_fallback = os.path.join(self.temp_dir, "normalized_no_music.mp4")
            ok = self._normalize_audio_track(stitched_path, normalized_fallback)
            if ok and os.path.exists(normalized_fallback):
                os.replace(normalized_fallback, output_path)
            else:
                os.replace(stitched_path, output_path)

        print(f"✅ FINAL VIDEO SAVED: {output_path}")

        if stitched_path != output_path and os.path.exists(stitched_path):
            try:
                os.remove(stitched_path)
            except Exception:
                pass

        # Nettoyage des clips de scène individuels (scene_*.mp4) maintenant
        # que le montage final est produit — évite l'accumulation disque.
        self._cleanup_scene_temp_files(video_paths)

        return output_path
