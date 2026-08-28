import os
import queue
import random
import shutil
import signal
import subprocess
import threading
import time

import ffmpeg


class FFmpegTimeoutError(Exception):
    """Levée quand un appel ffmpeg dépasse le timeout dur configuré."""
    pass


class Composer:
    """
    Compositeur vidéo vertical 1080x1920 orienté documentaire historique / mystère.

    Hybride Ultime (Prod + V3) optimisé pour CI/CD :
    - Gestion multi-assets (1 à N médias par scène)
    - Effets visuels Zoompan ultra-optimisés (Scale 1200px pre-zoom, input image statique)
    - Correction stricte du typage des assets entrant pour prévenir les Exit code 124
    - Gestion dynamique des musiques de fond et ducking broadcast-standard
    """

    def __init__(self):
        self.temp_dir = os.path.join(os.getcwd(), "assets", "temp")
        self.final_dir = os.path.join(os.getcwd(), "assets", "final")
        self.music_dir = os.path.join(os.getcwd(), "assets", "music")
        self.images_dir = os.path.join(os.getcwd(), "assets", "images")

        os.makedirs(self.temp_dir, exist_ok=True)
        os.makedirs(self.final_dir, exist_ok=True)
        os.makedirs(self.music_dir, exist_ok=True)
        os.makedirs(self.images_dir, exist_ok=True)

        # Transitions sobres
        self.transitions = ["fade", "fade"]
        self.current_bg_music_path = None

        # Branding Minute Mystère
        self.watermark_path = os.path.join(
            self.images_dir,
            "minute_mystere_watermark.png"
        )
        self.watermark_width = 205
        self.watermark_opacity = 0.72
        self.watermark_x = 42
        self.watermark_y = 48

        self.video_width = 1080
        self.video_height = 1920
        self.fps = 30

        # Mix documentaire (Broadcast standard)
        self.voice_gain = 1.08
        self.music_gain = 0.085
        self.music_fade_duration = 2.5
        self.transition_duration = 0.38
        
        self.fast_preset = "veryfast"
        self.final_preset = "medium"

        # Timeouts de sécurité (Ajustés pour runners CI/CD standard)
        self.timeout_scene_render = 360
        self.timeout_merge_pair = 150
        self.timeout_concat_global = 300
        self.timeout_music_mix = 150
        self.timeout_normalize = 90
        self.timeout_watermark = 150

        # Style des sous-titres premium
        self.subtitle_style = (
            "FontName=DejaVu Sans,FontSize=24,Bold=1,"
            "PrimaryColour=&H00FFFFFF,SecondaryColour=&H00FFFFFF,"
            "OutlineColour=&H00000000,BackColour=&H78000000,"
            "BorderStyle=3,Outline=1.5,Shadow=0,"
            "Alignment=2,MarginL=70,MarginR=70,MarginV=125"
        )

        self.source_credit_y = "h-520"
        self.source_credit_size = 18
        self.source_credit_alpha = 0.52

        self.watermark_font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

        # Mapping des crédits visuels
        self.source_credit_labels = {
            "wiki": "Source : Wikimedia Commons",
            "wikimedia": "Source : Wikimedia Commons",
            "openverse": "Source : Openverse",
            "video": "Illustration : Pexels / Pixabay",
            "pexels": "Illustration : Pexels / Pixabay",
            "pixabay": "Illustration : Pexels / Pixabay",
            "videvo": "Illustration : Pexels / Pixabay",
            "ai": "Illustration générée par IA",
        }

    # ------------------------------------------------------------------
    # GESTION DES MUSIQUES DE FOND (MULTI-PISTES)
    # ------------------------------------------------------------------

    def set_background_music(self, mood="intriguing"):
        if not os.path.exists(self.music_dir):
            self.current_bg_music_path = None
            return

        available_tracks = [f for f in os.listdir(self.music_dir) if f.lower().endswith(".mp3")]

        if not available_tracks:
            print("      ⚠️ Aucune musique trouvée dans assets/music/ !", flush=True)
            self.current_bg_music_path = None
            return

        matching_tracks = [f for f in available_tracks if mood.lower() in f.lower()]
        chosen_track = random.choice(matching_tracks) if matching_tracks else random.choice(available_tracks)
        
        self.current_bg_music_path = os.path.join(self.music_dir, chosen_track)
        print(f"      🎵 Musique sélectionnée : {chosen_track}", flush=True)

    # ------------------------------------------------------------------
    # UTILITAIRES & ROBUSTESSE
    # ------------------------------------------------------------------

    def _get_ffmpeg_error_text(self, error):
        stderr = getattr(error, "stderr", None)
        if stderr:
            if isinstance(stderr, bytes):
                try: return stderr.decode("utf8", errors="ignore")
                except Exception: return str(stderr)
            return str(stderr)
        return str(error)

    def _run(self, runner, timeout, label):
        """Exécution FFmpeg threadée avec Timeout dur."""
        args = runner.compile(overwrite_output=True)
        print(f"      🔧 CMD [{label}] : {' '.join(args)}", flush=True)

        args = [args[0], "-stats_period", "5", "-nostdin"] + args[1:]
        t0 = time.time()
        print(f"      ⏳ [{label}] ffmpeg démarré (timeout={timeout}s)...", flush=True)

        try:
            proc = subprocess.Popen(
                args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                text=True, bufsize=1, preexec_fn=os.setsid if os.name == "posix" else None,
            )
        except FileNotFoundError as e:
            raise RuntimeError(f"[{label}] ffmpeg introuvable : {e}")

        line_queue = queue.Queue()

        def _reader():
            try:
                for line in iter(proc.stderr.readline, ""):
                    line_queue.put(line)
            except Exception: pass
            finally:
                line_queue.put(None)

        reader_thread = threading.Thread(target=_reader, daemon=True)
        reader_thread.start()

        def _kill_process():
            try:
                if os.name == "posix": os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                else: proc.kill()
            except Exception: pass
            try: proc.wait(timeout=10)
            except Exception: pass

        last_progress_line = ""
        stderr_lines = []
        reader_done = False

        while True:
            elapsed = time.time() - t0
            if elapsed > timeout:
                _kill_process()
                raise FFmpegTimeoutError(f"{label}: timeout après {timeout}s (Progression : {last_progress_line})")

            try: line = line_queue.get(timeout=0.5)
            except queue.Empty:
                if reader_done and proc.poll() is not None: break
                continue

            if line is None:
                reader_done = True
                if proc.poll() is not None: break
                continue

            stderr_lines.append(line)
            if len(stderr_lines) > 40: stderr_lines.pop(0)

            if "frame=" in line:
                last_progress_line = line.strip()
                print(f"         … [{label}] {time.time() - t0:.0f}s | {last_progress_line}", flush=True)

        reader_thread.join(timeout=5)
        returncode = proc.returncode

        if returncode != 0:
            stderr_text = "".join(stderr_lines)
            print(f"      ❌ [{label}] échec ffmpeg (code {returncode}) en {time.time() - t0:.1f}s", flush=True)
            raise ffmpeg.Error("ffmpeg", None, stderr_text.encode("utf8"))

        print(f"      ✅ [{label}] terminé en {time.time() - t0:.1f}s", flush=True)
        return returncode

    def get_duration(self, filepath):
        try: return float(ffmpeg.probe(filepath)["format"]["duration"])
        except Exception: return 0.0

    def _escape_path_for_filter(self, path):
        return str(path).replace("\\", "/").replace(":", "\\:").replace("'", r"\'")

    def _escape_drawtext(self, text):
        return str(text).replace("\\", r"\\").replace(":", r"\:").replace("'", r"\'").replace(",", r"\,")

    def _normalize_assets_list(self, assets):
        if not assets: return []
        if isinstance(assets, dict): return [p for p in assets.values() if p]
        if isinstance(assets, (list, tuple)):
            res = []
            for item in assets:
                if isinstance(item, dict): res.extend([p for p in item.values() if p])
                elif item: res.append(str(item))
            return res
        return [str(assets)]

    def _is_video_file(self, path):
        """Identification stricte du format pour éviter le gel du demuxer."""
        if not path or not os.path.exists(path) or os.path.getsize(path) == 0: 
            return False
            
        filename = os.path.basename(path).lower()
        
        # 1. Analyse frontale des extensions d'images connues
        if filename.endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp")): 
            return False
            
        # 2. Analyse frontale des extensions vidéos connues
        if filename.endswith((".mp4", ".mov", ".webm", ".avi", ".mkv", ".m4v")): 
            return True

        # 3. Validation approfondie en dernier recours
        if "video" in filename:
            try:
                probe = ffmpeg.probe(path)
                for stream in probe.get("streams", []):
                    if stream.get("codec_type") == "video":
                        codec = stream.get("codec_name", "").lower()
                        if codec not in ["png", "mjpeg", "jpeg", "webp", "bmp"]: 
                            return True
            except Exception: 
                # Si erreur de lecture, on refuse le statut vidéo pour la sécurité du pipeline
                return False 
                
        return False

    def _resolve_source_credit(self, path_a):
        file_name = str(path_a).lower()
        for token, label in self.source_credit_labels.items():
            if f"_{token}_" in file_name or file_name.startswith(f"{token}_"): return label
        if "wiki" in file_name or "wikimedia" in file_name: return "Source : Wikimedia Commons"
        if "openverse" in file_name: return "Source : Openverse"
        if any(token in file_name for token in ("pexels", "pixabay", "videvo", "video")): return "Illustration : Pexels / Pixabay"
        if any(token in file_name for token in ("generated", "ai_", "midjourney", "gemini", "_ai_")): return "Illustration générée par IA"
        return "Illustration"

    # ------------------------------------------------------------------
    # WATERMARK
    # ------------------------------------------------------------------

    def add_watermark(self, input_video_path, output_video_path):
        if not os.path.exists(self.watermark_path):
            print(f"⚠️ Filigrane introuvable : {self.watermark_path}", flush=True)
            return False
        try:
            video = ffmpeg.input(input_video_path)
            logo = ffmpeg.input(self.watermark_path, format="image2", loop=1, framerate=self.fps).video
            logo = (
                logo.filter("scale", self.watermark_width, -1, force_original_aspect_ratio="decrease")
                .filter("format", "rgba")
                .filter("colorchannelmixer", aa=self.watermark_opacity)
            )
            watermarked_video = ffmpeg.overlay(
                video.video, logo, x=self.watermark_x, y=self.watermark_y, eof_action="repeat", shortest=1
            )
            runner = ffmpeg.output(
                watermarked_video, video.audio, output_video_path,
                vcodec="libx264", acodec="aac", audio_bitrate="192k",
                pix_fmt="yuv420p", r=self.fps, crf=18, preset=self.final_preset, movflags="faststart", shortest=None
            )
            self._run(runner, timeout=self.timeout_watermark, label="watermark")
            print(f"      Filigrane Minute Mystère ajouté ({self.watermark_width}px)", flush=True)
            return True
        except Exception as e:
            msg = self._get_ffmpeg_error_text(e)
            print(f"⚠️ Watermark failed: {msg}", flush=True)
            return False

    def add_watermark_text(self, input_video_path, output_video_path, channel_name="@MinuteMystere"):
        return self.add_watermark(input_video_path, output_video_path)

    # ------------------------------------------------------------------
    # RENDU D'UNE SCÈNE (MULTI-ASSETS + ZOOMPAN OPTIMISÉ CI/CD)
    # ------------------------------------------------------------------

    def process_scene(self, scene, assets, bg_video_path=None, bg_offset=0.0):
        scene_id = scene["id"]
        audio_path = scene.get("audio_path")
        total_duration = float(scene["duration"])

        output_path = os.path.join(self.temp_dir, f"scene_{scene_id}_rendered.mp4")

        if not audio_path or not os.path.exists(audio_path):
            return None

        print(f"      ▶️ Scène {scene_id} : début du rendu (durée cible {total_duration:.1f}s)...", flush=True)

        try:
            input_audio = ffmpeg.input(audio_path)
            source_for_credit = None

            if bg_video_path and os.path.exists(bg_video_path):
                source_duration = self.get_duration(bg_video_path)
                start_offset = bg_offset % source_duration if source_duration > 0 else 0.0

                video_stream = (
                    ffmpeg.input(bg_video_path, stream_loop=-1, ss=start_offset)
                    .filter("trim", duration=total_duration)
                    .filter("scale", self.video_width, self.video_height, force_original_aspect_ratio="increase")
                    .filter("crop", self.video_width, self.video_height)
                    .setpts("PTS-STARTPTS")
                )

            else:
                asset_list = self._normalize_assets_list(assets)
                valid_assets = [p for p in asset_list if p and os.path.exists(p) and os.path.getsize(p) > 0]

                if not valid_assets:
                    raise ValueError(f"Scene {scene_id}: aucun asset valide trouvé sur le disque.")

                source_for_credit = valid_assets[0]
                num_assets = len(valid_assets)
                chunk_duration = total_duration / num_assets

                streams = []

                for idx, path in enumerate(valid_assets):
                    print(f"         📷 Asset {idx + 1}/{num_assets} : {os.path.basename(path)}", flush=True)

                    if self._is_video_file(path):
                        # VIDÉO : Limitation du temps dès l'input (-t)
                        s = (
                            ffmpeg.input(path, stream_loop=-1, t=chunk_duration)
                            .filter("scale", self.video_width, self.video_height, force_original_aspect_ratio="increase")
                            .filter("crop", self.video_width, self.video_height)
                            .setpts("PTS-STARTPTS")
                        )
                    else:
                        # IMAGE : Entrée brute, suppression de loop=1 et t= pour le bon fonctionnement de zoompan
                        frames = max(int(chunk_duration * self.fps), 1)
                        z_expr = "min(zoom+0.0009,1.14)" if idx % 2 == 0 else "if(eq(on,1),1.07,max(zoom-0.0008,1.0))"

                        s = (
                            ffmpeg.input(path)
                            .filter("scale", 1200, -1)
                            .filter("zoompan", z=z_expr, d=frames, s=f"{self.video_width}x{self.video_height}", fps=self.fps)
                            .setpts("PTS-STARTPTS")
                        )

                    streams.append(s)

                video_stream = ffmpeg.concat(*streams, v=1, a=0) if len(streams) > 1 else streams[0]

            # Crédit source
            if not bg_video_path and source_for_credit:
                source_text = self._resolve_source_credit(source_for_credit)
                if source_text:
                    video_stream = video_stream.filter(
                        "drawtext", text=self._escape_drawtext(source_text), fontfile=self.watermark_font_path,
                        fontcolor=f"white@{self.source_credit_alpha}", fontsize=self.source_credit_size,
                        box=0, shadowcolor="black@0.75", shadowx=1, shadowy=1, x="30", y=self.source_credit_y
                    )

            # Sous-titres
            srt_path = scene.get("srt_path")
            if srt_path and os.path.exists(srt_path):
                video_stream = video_stream.filter(
                    "subtitles", filename=self._escape_path_for_filter(srt_path), force_style=self.subtitle_style
                )

            # Encodage
            runner = ffmpeg.output(
                video_stream, input_audio, output_path,
                vcodec="libx264", acodec="aac", audio_bitrate="192k",
                pix_fmt="yuv420p", r=self.fps, crf=20, preset=self.fast_preset, movflags="faststart", shortest=None
            )

            self._run(runner, timeout=self.timeout_scene_render, label=f"scène {scene_id}")
            return output_path

        except Exception as e:
            print(f"❌ Render Fail Scene {scene_id}: {self._get_ffmpeg_error_text(e)}", flush=True)
            return None

    # ------------------------------------------------------------------
    # RENDU DE TOUTES LES SCÈNES
    # ------------------------------------------------------------------

    def render_all_scenes(self, script_data, video_asset_lists, bg_video_path=None):
        rendered_paths = []
        bg_cursor = 0.0

        for i, scene in enumerate(script_data):
            current_assets = video_asset_lists[i] if i < len(video_asset_lists) else None
            output_path = self.process_scene(
                scene, current_assets, bg_video_path=bg_video_path, bg_offset=bg_cursor
            )
            bg_cursor += float(scene["duration"])
            if output_path:
                rendered_paths.append(output_path)

        return rendered_paths

    # ------------------------------------------------------------------
    # ASSEMBLAGE (Global Xfade + Séquentiel)
    # ------------------------------------------------------------------

    def _merge_two_clips(self, clip_a, clip_b, output_path, trans_dur=None):
        trans_dur = trans_dur if trans_dur is not None else self.transition_duration
        dur_a = self.get_duration(clip_a)
        offset = max(dur_a - trans_dur, 0)
        effect = random.choice(self.transitions)

        input_a = ffmpeg.input(clip_a)
        input_b = ffmpeg.input(clip_b)

        v_stream = ffmpeg.filter([input_a.video, input_b.video], "xfade", transition=effect, duration=trans_dur, offset=offset)
        a_stream = ffmpeg.filter([input_a.audio, input_b.audio], "acrossfade", d=trans_dur)

        runner = ffmpeg.output(
            v_stream, a_stream, output_path,
            vcodec="libx264", acodec="aac", audio_bitrate="192k",
            pix_fmt="yuv420p", crf=18, preset=self.fast_preset, movflags="faststart"
        )
        self._run(runner, timeout=self.timeout_merge_pair, label="merge fade (2 clips)")
        return effect, offset

    def _concat_all_with_xfade(self, video_paths, output_path):
        if len(video_paths) == 1:
            shutil.copy2(video_paths[0], output_path)
            return True

        durations = [self.get_duration(p) for p in video_paths]
        if any(d <= 0 for d in durations): return False

        inputs = [ffmpeg.input(p) for p in video_paths]
        trans_dur = self.transition_duration

        video_stream = inputs[0].video
        audio_stream = inputs[0].audio
        cumulative_duration = durations[0]

        for i in range(1, len(inputs)):
            offset = max(cumulative_duration - trans_dur, 0)
            video_stream = ffmpeg.filter([video_stream, inputs[i].video], "xfade", transition="fade", duration=trans_dur, offset=offset)
            audio_stream = ffmpeg.filter([audio_stream, inputs[i].audio], "acrossfade", d=trans_dur)
            cumulative_duration = cumulative_duration + durations[i] - trans_dur

        runner = ffmpeg.output(
            video_stream, audio_stream, output_path,
            vcodec="libx264", acodec="aac", audio_bitrate="192k",
            pix_fmt="yuv420p", crf=18, preset=self.fast_preset, movflags="faststart"
        )
        
        try:
            self._run(runner, timeout=self.timeout_concat_global, label=f"xfade global ({len(video_paths)} clips)")
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # NORMALISATION AUDIO
    # ------------------------------------------------------------------

    def _normalize_audio_track(self, input_video_path, output_video_path):
        try:
            src = ffmpeg.input(input_video_path)
            normalized_audio = src.audio.filter("loudnorm", I=-16, TP=-1.5, LRA=9)
            runner = ffmpeg.output(
                src.video, normalized_audio, output_video_path,
                vcodec="copy", acodec="aac", audio_bitrate="192k", movflags="faststart"
            )
            self._run(runner, timeout=self.timeout_normalize, label="normalisation audio")
            return True
        except Exception as e:
            print(f"⚠️ Loudnorm failed: {self._get_ffmpeg_error_text(e)}", flush=True)
            return False

    # ------------------------------------------------------------------
    # MUSIQUE DE FOND DYNAMIQUE + DUCKING
    # ------------------------------------------------------------------

    def _mix_background_music(self, stitched_path, output_path):
        if not self.current_bg_music_path or not os.path.exists(self.current_bg_music_path):
            return False

        try:
            video_duration = self.get_duration(stitched_path)
            if video_duration <= 0: raise ValueError("Durée vidéo invalide.")

            fade_start = max(video_duration - self.music_fade_duration, 0)
            voice = ffmpeg.input(stitched_path)
            music = ffmpeg.input(self.current_bg_music_path, stream_loop=-1)

            voice_audio = (
                voice.audio
                .filter("aformat", sample_fmts="fltp", sample_rates=48000, channel_layouts="stereo")
                .filter("volume", self.voice_gain)
                .filter("atrim", duration=video_duration)
                .filter("asetpts", "PTS-STARTPTS")
            )

            music_audio = (
                music.audio
                .filter("aformat", sample_fmts="fltp", sample_rates=48000, channel_layouts="stereo")
                .filter("volume", self.music_gain)
                .filter("atrim", duration=video_duration)
                .filter("asetpts", "PTS-STARTPTS")
                .filter("afade", type="in", start_time=0, duration=min(1.2, video_duration))
                .filter("afade", type="out", start_time=fade_start, duration=self.music_fade_duration)
            )

            voice_splits = voice_audio.split()
            music_splits = music_audio.split()

            ducked_music = ffmpeg.filter(
                [music_splits[0], voice_splits[0]],
                "sidechaincompress", threshold=0.035, ratio=5, attack=30, release=450, makeup=1
            )

            mixed_audio = (
                ffmpeg.filter(
                    [voice_splits[1], ducked_music], "amix", inputs=2, duration="first", dropout_transition=2, normalize=0
                )
                .filter("loudnorm", I=-16, TP=-1.5, LRA=9)
            )

            final_runner = ffmpeg.output(
                voice.video, mixed_audio, output_path,
                vcodec="libx264", acodec="aac", audio_bitrate="192k",
                pix_fmt="yuv420p", movflags="faststart", preset=self.fast_preset
            )

            self._run(final_runner, timeout=self.timeout_music_mix, label="mixage musique")
            return True

        except Exception as e:
            print(f"⚠️ Music mix failed: {self._get_ffmpeg_error_text(e)}", flush=True)
            return False

    # ------------------------------------------------------------------
    # FINALISATION
    # ------------------------------------------------------------------

    def concatenate_with_transitions(self, video_paths, output_filename="final_short.mp4"):
        raw_final_output_path = os.path.join(self.temp_dir, "raw_final_stitched.mp4")
        output_path = os.path.join(self.final_dir, output_filename)

        if os.path.exists(output_path):
            try: os.remove(output_path)
            except Exception: pass

        if not video_paths: return None

        merge_step_files = []
        stitched_path = os.path.join(self.temp_dir, "stitched_all.mp4")

        success = self._concat_all_with_xfade(video_paths, stitched_path)

        if not success:
            print("↩️ Fallback : fusion séquentielle clip par clip.", flush=True)
            if len(video_paths) == 1:
                stitched_path = video_paths[0]
            else:
                courant = video_paths[0]
                for i in range(1, len(video_paths)):
                    suivant = video_paths[i]
                    merge_output = os.path.join(self.temp_dir, f"merge_step_{i}.mp4")
                    try:
                        effect, offset = self._merge_two_clips(courant, suivant, merge_output)
                        print(f"      Transition {i}: {effect} (offset={offset:.2f}s)", flush=True)
                    except Exception as e:
                        print(f"❌ Stitching Error at step {i}: {self._get_ffmpeg_error_text(e)}", flush=True)
                        self._cleanup_temp_files(merge_step_files)
                        return None
                    
                    if courant.startswith(os.path.join(self.temp_dir, "merge_step_")):
                        merge_step_files.append(courant)
                    courant = merge_output
                stitched_path = courant

        music_success = self._mix_background_music(stitched_path, raw_final_output_path)
        if not music_success:
            self._fallback_no_music(stitched_path, raw_final_output_path)

        watermark_success = self.add_watermark(raw_final_output_path, output_path)
        if not watermark_success:
            print("      ⚠️ Filigrane non appliqué : copie de la vidéo sans watermark.", flush=True)
            shutil.copy2(raw_final_output_path, output_path)

        if os.path.exists(raw_final_output_path):
            try: os.remove(raw_final_output_path)
            except Exception: pass

        self._cleanup_temp_files(video_paths + merge_step_files, keep=output_path)
        if stitched_path not in video_paths and stitched_path != output_path:
            self._cleanup_temp_files([stitched_path], keep=output_path)

        return output_path

    def _fallback_no_music(self, stitched_path, raw_final_output_path):
        normalized_fallback = os.path.join(self.temp_dir, "normalized_no_music.mp4")
        ok = self._normalize_audio_track(stitched_path, normalized_fallback)
        if ok and os.path.exists(normalized_fallback):
            os.replace(normalized_fallback, raw_final_output_path)
        else:
            shutil.copy2(stitched_path, raw_final_output_path)

    # ------------------------------------------------------------------
    # NETTOYAGE
    # ------------------------------------------------------------------

    def _cleanup_temp_files(self, filepaths, keep=None):
        for filepath in filepaths:
            if not filepath or filepath == keep: continue
            if os.path.exists(filepath):
                try: os.remove(filepath)
                except Exception: pass
