import os
import random
import shutil
import subprocess
import time
import ffmpeg


class FFmpegTimeoutError(Exception):
    """Levée quand un appel ffmpeg dépasse le timeout dur configuré."""
    pass


class Composer:
    """
    Compositeur video verticale 1080x1920 oriente documentaire / mystere.

    OPTIMISATION PERFORMANCE (fix timeout CI) :
    - fusion globale xfade en un seul appel ffmpeg (O(n)) au lieu de N-1
      appels sequentiels (O(n^2)), + preset veryfast pour les encodages
      intermediaires ;
    - logs de progression avec timestamp + flush=True à CHAQUE étape
      ffmpeg (le code d'origine ne loguait qu'en cas d'erreur, ce qui
      rendait impossible de savoir où un run se bloquait) ;
    - timeout dur par appel ffmpeg via subprocess.run(timeout=...) : un
      appel qui dépasse son budget est tué et lève FFmpegTimeoutError au
      lieu de bloquer le pipeline jusqu'à la limite globale de 85 min ;
    - zoompan : prescale ramené de 2200px à 1400px de large avant le
      zoom, ce qui réduit fortement le coût par frame (zoompan est
      notoirement lent, sans accélération matérielle).
    """

    def __init__(self):
        self.temp_dir = os.path.join(os.getcwd(), "assets", "temp")
        self.final_dir = os.path.join(os.getcwd(), "assets", "final")
        self.music_dir = os.path.join(os.getcwd(), "assets", "music")
        self.images_dir = os.path.join(os.getcwd(), "assets", "images")

        for d in [self.temp_dir, self.final_dir, self.music_dir, self.images_dir]:
            os.makedirs(d, exist_ok=True)

        self.transitions = ["fade", "fade"]
        self.current_bg_music_path = None

        self.watermark_path = os.path.join(self.images_dir, "minute_mystere_watermark.png")
        self.watermark_width = 160
        self.watermark_opacity = 0.55
        self.watermark_x = 42
        self.watermark_y = 48

        self.video_width = 1080
        self.video_height = 1920
        self.fps = 30

        self.voice_gain = 1.05
        self.music_gain = 0.055
        self.music_fade_duration = 2.5
        self.transition_duration = 0.22

        self.fast_preset = "veryfast"
        self.final_preset = "medium"

        # Largeur de prescale avant zoompan. 2200px était excessif pour
        # une sortie 1080 de large et faisait exploser le temps de calcul
        # par frame (zoompan traite chaque frame individuellement, sans
        # accélération). 1400px reste net en sortie 1080 tout en étant
        # nettement moins coûteux.
        self.zoompan_prescale_width = 1400

        # --- Timeouts durs par étape (en secondes) ---
        # Ajuste ces valeurs selon la puissance du runner CI. L'objectif
        # est qu'un appel individuel échoue proprement bien avant la
        # limite globale du job (ici 85 min), pour laisser le temps aux
        # fallbacks de s'exécuter et/ou d'avoir un message d'erreur clair.
        self.timeout_scene_render = 240        # rendu d'une scène individuelle
        self.timeout_merge_pair = 150           # fusion séquentielle de 2 clips
        self.timeout_concat_global = 300        # fusion xfade globale (tous les clips)
        self.timeout_music_mix = 150            # mixage musique de fond
        self.timeout_normalize = 90             # normalisation audio (sans musique)
        self.timeout_watermark = 150            # ajout du filigrane final

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

        self.source_credit_labels = {
            "wiki": "Source : Wikimedia Commons",
            "wikimedia": "Source : Wikimedia Commons",
            "openverse": "Source : Openverse",
            "video": "Illustration : Pexels / Pixabay",
            "pexels": "Illustration : Pexels / Pixabay",
            "pixabay": "Illustration : Pexels / Pixabay",
            "videvo": "Illustration : Pexels / Pixabay",
            "ai": "Illustration generee par IA",
        }

    # ------------------------------------------------------------------
    # Coeur du fix : exécution d'un graphe ffmpeg-python avec timeout dur
    # et logs de progression systématiques.
    # ------------------------------------------------------------------
    def _run(self, runner, timeout, label):
        """
        Exécute un graphe ffmpeg-python (via subprocess.run + timeout dur)
        en loguant début / fin / durée, au lieu du .run(quiet=True)
        d'origine qui ne renvoyait rien tant que ça n'avait pas planté.

        Lève FFmpegTimeoutError si le process dépasse `timeout` secondes
        (le process est alors tué proprement par subprocess).
        Lève ffmpeg.Error si ffmpeg retourne un code non nul.
        """
        # On force ffmpeg à émettre sa progression (frame=N, speed=...) sur
        # stderr à intervalle régulier (-stats_period), pour pouvoir
        # distinguer en cas de timeout :
        #   - un VRAI hang (aucune frame produite, "frame=0" jusqu'à la fin)
        #   - une simple LENTEUR CPU (les frames avancent, juste trop lentement
        #     pour le budget de timeout donné -> augmenter le timeout suffit)
        # Sans ça, un TIMEOUT ne nous dit que "ça a dépassé Xs", pas pourquoi.
        args = runner.compile(overwrite_output=True)
        args = [args[0], "-stats_period", "5", "-nostdin"] + args[1:]

        t0 = time.time()
        print(f"      ⏳ [{label}] ffmpeg démarré (timeout={timeout}s)...", flush=True)

        last_progress_line = ""
        stderr_lines = []

        try:
            proc = subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except FileNotFoundError as e:
            raise RuntimeError(f"[{label}] ffmpeg introuvable sur ce runner : {e}")

        try:
            while True:
                line = proc.stderr.readline()
                if line:
                    stderr_lines.append(line)
                    if len(stderr_lines) > 40:
                        stderr_lines.pop(0)
                    if "frame=" in line:
                        last_progress_line = line.strip()
                        elapsed_now = time.time() - t0
                        print(f"         … [{label}] {elapsed_now:.0f}s écoulées | {last_progress_line}", flush=True)
                elif proc.poll() is not None:
                    break

                if time.time() - t0 > timeout:
                    proc.kill()
                    proc.wait(timeout=10)
                    elapsed = time.time() - t0
                    if last_progress_line:
                        print(
                            f"      ⏱️ [{label}] TIMEOUT après {elapsed:.1f}s — process tué. "
                            f"Dernière progression connue : {last_progress_line}",
                            flush=True,
                        )
                        raise FFmpegTimeoutError(
                            f"{label}: timeout après {timeout}s (encodage en cours mais trop lent — "
                            f"dernière progression : {last_progress_line})"
                        )
                    else:
                        print(
                            f"      ⏱️ [{label}] TIMEOUT après {elapsed:.1f}s — process tué. "
                            f"AUCUNE progression détectée (vrai blocage, pas juste de la lenteur).",
                            flush=True,
                        )
                        raise FFmpegTimeoutError(
                            f"{label}: timeout après {timeout}s (0 frame produite — hang probable, "
                            f"pas un simple problème de vitesse)"
                        )
        finally:
            if proc.stderr:
                proc.stderr.close()

        elapsed = time.time() - t0
        returncode = proc.returncode
        if returncode != 0:
            stderr_text = "".join(stderr_lines)
            print(f"      ❌ [{label}] échec ffmpeg (code {returncode}) en {elapsed:.1f}s", flush=True)
            raise ffmpeg.Error("ffmpeg", None, stderr_text.encode("utf8"))

        print(f"      ✅ [{label}] terminé en {elapsed:.1f}s", flush=True)
        return returncode

    def set_background_music(self, mood="intriguing"):
        if not os.path.exists(self.music_dir):
            self.current_bg_music_path = None
            return
        available_tracks = [f for f in os.listdir(self.music_dir) if f.endswith('.mp3')]
        if not available_tracks:
            print("      ⚠️ Aucune musique trouvee dans assets/music/ !")
            self.current_bg_music_path = None
            return
        matching_tracks = [f for f in available_tracks if mood.lower() in f.lower()]
        chosen_track = random.choice(matching_tracks) if matching_tracks else random.choice(available_tracks)
        self.current_bg_music_path = os.path.join(self.music_dir, chosen_track)
        print(f"      🎵 Musique selectionnee : {chosen_track} (Mood cible: {mood})")

    def _get_transition_for_scene(self, scene):
        transition = scene.get("transition", "cut")
        if transition == "cut":
            return None
        if transition == "fade":
            return "fade"
        return "fade"

    def get_duration(self, filepath):
        try:
            probe = ffmpeg.probe(filepath)
            return float(probe["format"]["duration"])
        except Exception:
            return 0.0

    def _escape_path_for_filter(self, path):
        return str(path).replace("\\", "/").replace(":", "\\:").replace("'", r"\'")

    def _escape_drawtext(self, text):
        return str(text).replace("\\", r"\\").replace(":", r"\:").replace("'", r"\'").replace(",", r"\,")

    def _is_video_file(self, path):
        return str(path).lower().endswith((".mp4", ".mov", ".webm", ".avi", ".mkv", ".m4v"))

    def _resolve_source_credit(self, path_a):
        file_name = str(path_a).lower()
        for token, label in self.source_credit_labels.items():
            if f"_{token}_" in file_name or file_name.startswith(f"{token}_"):
                return label
        if "wiki" in file_name or "wikimedia" in file_name:
            return "Source : Wikimedia Commons"
        if "openverse" in file_name:
            return "Source : Openverse"
        if any(token in file_name for token in ("pexels", "pixabay", "videvo", "video")):
            return "Illustration : Pexels / Pixabay"
        if any(token in file_name for token in ("generated", "ai_", "midjourney", "gemini", "_ai_")):
            return "Illustration generee par IA"
        return "Illustration"

    def add_watermark(self, input_video_path, output_video_path):
        if not os.path.exists(self.watermark_path):
            print(f"⚠️ Filigrane introuvable : {self.watermark_path}")
            return False
        try:
            video = ffmpeg.input(input_video_path)
            logo = ffmpeg.input(self.watermark_path, format="image2", loop=1, framerate=self.fps).video
            logo = (
                logo
                .filter("scale", self.watermark_width, -1, force_original_aspect_ratio="decrease")
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
            return True
        except (ffmpeg.Error, FFmpegTimeoutError) as e:
            stderr = getattr(e, "stderr", None)
            msg = stderr.decode("utf8", errors="ignore") if stderr else str(e)
            print(f"⚠️ Watermark failed: {msg}")
            return False
        except Exception as e:
            print(f"⚠️ Watermark failed (exception inattendue) : {e}")
            return False

    def process_scene(self, scene, assets, bg_video_path=None, bg_offset=0.0):
        scene_id = scene["id"]
        audio_path = scene.get("audio_path")
        total_duration = float(scene["duration"])
        output_path = os.path.join(self.temp_dir, f"scene_{scene_id}_rendered.mp4")

        if not audio_path or not os.path.exists(audio_path):
            print(f"      ⚠️ Scene {scene_id} ignoree : aucun fichier audio valide (TTS probablement en echec).")
            return None

        t0 = time.time()
        print(f"      ▶️ Scene {scene_id} : début du rendu (durée cible {total_duration:.1f}s)...", flush=True)

        try:
            input_audio = ffmpeg.input(audio_path)

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
                source_for_credit = None
            else:
                if not assets:
                    raise ValueError(f"Scene {scene_id}: aucun asset fourni.")
                if not isinstance(assets, list):
                    if isinstance(assets, dict):
                        assets = list(assets.values())
                    else:
                        assets = [assets]
                valid_assets = [p for p in assets if p and os.path.exists(p)]
                if not valid_assets:
                    raise ValueError(f"Scene {scene_id}: les assets fournis sont introuvables.")
                num_assets = len(valid_assets)
                chunk_duration = total_duration / num_assets
                streams = []
                for idx, path in enumerate(valid_assets):
                    if self._is_video_file(path):
                        stream = (
                            ffmpeg.input(path, stream_loop=-1)
                            .filter("trim", duration=chunk_duration)
                            .filter("scale", self.video_width, self.video_height, force_original_aspect_ratio="increase")
                            .filter("crop", self.video_width, self.video_height)
                            .setpts("PTS-STARTPTS")
                        )
                    else:
                        frames = max(int(chunk_duration * self.fps), 1)
                        zoom_expr = "min(zoom+0.0009,1.14)" if idx % 2 == 0 else "if(eq(on,1),1.07,max(zoom-0.0008,1.0))"
                        stream = (
                            ffmpeg.input(path, format="image2", loop=1, framerate=self.fps, t=chunk_duration)
                            # Prescale réduit (2200 -> zoompan_prescale_width) : zoompan
                            # recalcule chaque frame individuellement, donc partir d'une
                            # image moins large réduit fortement le coût CPU par frame.
                            .filter("scale", self.zoompan_prescale_width, -1)
                            .filter("zoompan", z=zoom_expr, d=frames, s=f"{self.video_width}x{self.video_height}", fps=self.fps)
                            .setpts("PTS-STARTPTS")
                        )
                    streams.append(stream)
                if len(streams) > 1:
                    video_stream = ffmpeg.concat(*streams, v=1, a=0)
                else:
                    video_stream = streams[0]
                source_for_credit = valid_assets[0]

            if source_for_credit:
                source_text = self._resolve_source_credit(source_for_credit)
                if source_text:
                    video_stream = video_stream.filter(
                        "drawtext", text=self._escape_drawtext(source_text),
                        fontfile=self.watermark_font_path, fontcolor=f"white@{self.source_credit_alpha}",
                        fontsize=self.source_credit_size, box=0, shadowcolor="black@0.75",
                        shadowx=1, shadowy=1, x="30", y=self.source_credit_y
                    )

            srt_path = scene.get("srt_path")
            if srt_path and os.path.exists(srt_path):
                video_stream = video_stream.filter(
                    "subtitles", filename=self._escape_path_for_filter(srt_path), force_style=self.subtitle_style
                )

            runner = ffmpeg.output(
                video_stream, input_audio, output_path,
                vcodec="libx264", acodec="aac", audio_bitrate="192k",
                pix_fmt="yuv420p", r=self.fps, crf=20, preset=self.fast_preset, movflags="faststart", shortest=None
            )
            self._run(runner, timeout=self.timeout_scene_render, label=f"scène {scene_id}")
            print(f"      ✅ Scene {scene_id} rendue en {time.time() - t0:.1f}s au total.", flush=True)
            return output_path
        except FFmpegTimeoutError as e:
            print(f"❌ Render Fail Scene {scene_id} (TIMEOUT) : {e}", flush=True)
            return None
        except ffmpeg.Error as e:
            print(f"❌ Render Fail Scene {scene_id}: {e.stderr.decode('utf8', errors='ignore') if e.stderr else str(e)}", flush=True)
            return None
        except Exception as e:
            print(f"❌ Render Fail Scene {scene_id}: {e}", flush=True)
            return None

    def render_all_scenes(self, script_data, video_asset_lists, bg_video_path=None):
        rendered_paths = []
        bg_cursor = 0.0
        total = len(script_data)
        t_start = time.time()
        print(f"🎞️ Rendu de {total} scènes démarré...", flush=True)
        for i, scene in enumerate(script_data):
            print(f"   —— Scène {i + 1}/{total} (id={scene.get('id')}) ——", flush=True)
            current_assets = video_asset_lists[i] if i < len(video_asset_lists) else None
            output_path = self.process_scene(scene, current_assets, bg_video_path=bg_video_path, bg_offset=bg_cursor)
            bg_cursor += float(scene["duration"])
            if output_path:
                rendered_paths.append(output_path)
        print(
            f"🎞️ Rendu des scènes terminé : {len(rendered_paths)}/{total} réussies "
            f"en {time.time() - t_start:.1f}s.",
            flush=True,
        )
        return rendered_paths

    def _merge_two_clips(self, clip_a, clip_b, output_path, trans_dur=None, use_transition=True):
        dur_a = self.get_duration(clip_a)
        input_a = ffmpeg.input(clip_a)
        input_b = ffmpeg.input(clip_b)
        if not use_transition:
            joined_video = ffmpeg.concat(input_a.video, input_b.video, v=1, a=0)
            joined_audio = ffmpeg.concat(input_a.audio, input_b.audio, v=0, a=1)
            runner = ffmpeg.output(
                joined_video, joined_audio, output_path,
                vcodec="libx264", acodec="aac", audio_bitrate="192k",
                pix_fmt="yuv420p", crf=18, preset=self.fast_preset, movflags="faststart"
            )
            self._run(runner, timeout=self.timeout_merge_pair, label="merge cut (2 clips)")
            return "cut", 0
        trans_dur = trans_dur if trans_dur is not None else self.transition_duration
        offset = max(dur_a - trans_dur, 0)
        v_stream = ffmpeg.filter([input_a.video, input_b.video], "xfade", transition="fade", duration=trans_dur, offset=offset)
        a_stream = ffmpeg.filter([input_a.audio, input_b.audio], "acrossfade", d=trans_dur)
        runner = ffmpeg.output(
            v_stream, a_stream, output_path,
            vcodec="libx264", acodec="aac", audio_bitrate="192k",
            pix_fmt="yuv420p", crf=18, preset=self.fast_preset, movflags="faststart"
        )
        self._run(runner, timeout=self.timeout_merge_pair, label="merge fade (2 clips)")
        return "fade", offset

    def _concat_all_with_xfade(self, video_paths, output_path):
        if len(video_paths) == 1:
            shutil.copy2(video_paths[0], output_path)
            return True
        durations = [self.get_duration(p) for p in video_paths]
        if any(d <= 0 for d in durations):
            print("⚠️ Duree invalide detectee, fallback vers fusion sequentielle.")
            return False
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
        try:
            runner = ffmpeg.output(
                video_stream, audio_stream, output_path,
                vcodec="libx264", acodec="aac", audio_bitrate="192k",
                pix_fmt="yuv420p", crf=18, preset=self.fast_preset, movflags="faststart"
            )
            self._run(runner, timeout=self.timeout_concat_global, label=f"xfade global ({len(video_paths)} clips)")
            return True
        except FFmpegTimeoutError as e:
            print(f"⚠️ Fusion globale xfade en timeout, fallback sequentiel : {e}", flush=True)
            return False
        except ffmpeg.Error as e:
            print(f"⚠️ Fusion globale xfade echouee, fallback sequentiel : "
                  f"{e.stderr.decode('utf8', errors='ignore') if e.stderr else str(e)}", flush=True)
            return False

    def _mix_background_music(self, stitched_path, output_path):
        if not self.current_bg_music_path or not os.path.exists(self.current_bg_music_path):
            return False
        try:
            video_duration = self.get_duration(stitched_path)
            if video_duration <= 0:
                raise ValueError("Duree video invalide.")
            fade_start = max(video_duration - self.music_fade_duration, 0)
            voice = ffmpeg.input(stitched_path)
            music = ffmpeg.input(self.current_bg_music_path, stream_loop=-1)
            voice_audio = (
                voice.audio
                .filter("aformat", sample_fmts="fltp", sample_rates=48000, channel_layouts="stereo")
                .filter("volume", self.voice_gain)
                .filter("atrim", duration=video_duration).filter("asetpts", "PTS-STARTPTS")
            )
            music_audio = (
                music.audio
                .filter("aformat", sample_fmts="fltp", sample_rates=48000, channel_layouts="stereo")
                .filter("volume", self.music_gain)
                .filter("atrim", duration=video_duration).filter("asetpts", "PTS-STARTPTS")
                .filter("afade", type="in", start_time=0, duration=min(1.2, video_duration))
                .filter("afade", type="out", start_time=fade_start, duration=self.music_fade_duration)
            )
            voice_for_duck, voice_for_mix = voice_audio.filter_multi_output("asplit", 2)
            music_for_duck, music_for_mix = music_audio.filter_multi_output("asplit", 2)
            ducked_music = ffmpeg.filter(
                [music_for_duck, voice_for_duck], "sidechaincompress",
                threshold=0.035, ratio=5, attack=30, release=450, makeup=1
            )
            mixed_audio = (
                ffmpeg.filter([voice_for_mix, ducked_music], "amix", inputs=2, duration="first", dropout_transition=2, normalize=0)
                .filter("loudnorm", I=-16, TP=-1.5, LRA=9)
            )
            final_runner = ffmpeg.output(
                voice.video, mixed_audio, output_path,
                vcodec="libx264", acodec="aac", audio_bitrate="192k",
                pix_fmt="yuv420p", movflags="faststart", preset=self.fast_preset
            )
            self._run(final_runner, timeout=self.timeout_music_mix, label="mixage musique")
            return True
        except FFmpegTimeoutError as e:
            print(f"⚠️ Mixage musique en timeout : {e}", flush=True)
            return False
        except ffmpeg.Error:
            return False
        except Exception:
            return False

    def _normalize_audio_track(self, input_path, output_path):
        try:
            video = ffmpeg.input(input_path)
            audio = video.audio.filter("loudnorm", I=-16, TP=-1.5, LRA=9)
            runner = ffmpeg.output(
                video.video, audio, output_path,
                vcodec="copy", acodec="aac", audio_bitrate="192k",
                movflags="faststart"
            )
            self._run(runner, timeout=self.timeout_normalize, label="normalisation audio")
            return True
        except Exception as e:
            print(f"⚠️ Normalisation audio échouée : {e}", flush=True)
            return False

    def concatenate_with_transitions(self, video_paths, output_filename="final_short.mp4"):
        t_start = time.time()
        raw_final_output_path = os.path.join(self.temp_dir, "raw_final_stitched.mp4")
        output_path = os.path.join(self.final_dir, output_filename)
        if os.path.exists(output_path):
            try: os.remove(output_path)
            except Exception: pass
        if not video_paths:
            print("❌ Aucun clip à fusionner, abandon.", flush=True)
            return None

        print(f"🔗 Fusion de {len(video_paths)} clips...", flush=True)
        merge_step_files = []
        stitched_path = os.path.join(self.temp_dir, "stitched_all.mp4")
        success = self._concat_all_with_xfade(video_paths, stitched_path)
        if not success:
            print("↩️ Fallback : fusion sequentielle clip par clip.", flush=True)
            if len(video_paths) == 1:
                stitched_path = video_paths[0]
            else:
                courant = video_paths[0]
                for i in range(1, len(video_paths)):
                    suivant = video_paths[i]
                    merge_output = os.path.join(self.temp_dir, f"merge_step_{i}.mp4")
                    print(f"   🔗 Fusion séquentielle {i}/{len(video_paths) - 1}...", flush=True)
                    try:
                        effect, offset = self._merge_two_clips(courant, suivant, merge_output)
                    except (ffmpeg.Error, FFmpegTimeoutError) as e:
                        print(f"❌ Fusion séquentielle échouée à l'étape {i} : {e}", flush=True)
                        self._cleanup_temp_files(merge_step_files)
                        return None
                    if courant.startswith(os.path.join(self.temp_dir, "merge_step_")):
                        merge_step_files.append(courant)
                    courant = merge_output
                stitched_path = courant

        print("🎵 Mixage de la musique de fond...", flush=True)
        if self.current_bg_music_path and os.path.exists(self.current_bg_music_path):
            music_success = self._mix_background_music(stitched_path, raw_final_output_path)
            if not music_success:
                print("   ↩️ Musique indisponible/échouée, fallback sans musique (normalisation seule).", flush=True)
                self._fallback_no_music(stitched_path, raw_final_output_path)
        else:
            self._fallback_no_music(stitched_path, raw_final_output_path)

        print("🖼️ Ajout du filigrane...", flush=True)
        watermark_success = self.add_watermark(raw_final_output_path, output_path)
        if not watermark_success:
            print("   ↩️ Filigrane échoué, copie du fichier sans filigrane.", flush=True)
            shutil.copy2(raw_final_output_path, output_path)

        if os.path.exists(raw_final_output_path):
            try: os.remove(raw_final_output_path)
            except Exception: pass

        self._cleanup_temp_files(video_paths + merge_step_files, keep=output_path)
        if stitched_path not in video_paths and stitched_path != output_path:
            self._cleanup_temp_files([stitched_path], keep=output_path)

        print(f"✅ Vidéo finale prête en {time.time() - t_start:.1f}s : {output_path}", flush=True)
        return output_path

    def _fallback_no_music(self, stitched_path, raw_final_output_path):
        normalized_fallback = os.path.join(self.temp_dir, "normalized_no_music.mp4")
        ok = self._normalize_audio_track(stitched_path, normalized_fallback)
        if ok and os.path.exists(normalized_fallback):
            os.replace(normalized_fallback, raw_final_output_path)
        else:
            shutil.copy2(stitched_path, raw_final_output_path)

    def _cleanup_temp_files(self, filepaths, keep=None):
        for filepath in filepaths:
            if not filepath or filepath == keep:
                continue
            if os.path.exists(filepath):
                try:
                    os.remove(filepath)
                except Exception:
                    pass
