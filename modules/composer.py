import os
import random
import shutil
import ffmpeg



class Composer:
    """
    Compositeur vidéo vertical 1080x1920 orienté documentaire / mystère.


    Pipeline visuel :
        scènes -> sous-titres -> crédit source
               -> assemblage discret par fondus
               -> mix voix + musique avec ducking
               -> normalisation finale
               -> filigrane de marque premium


    Le filigrane n'est plus un drawtext : il utilise le logo PNG
    assets/images/minute_mystere_watermark.png.
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


        # Documentaire mystère : transitions sobres.
        self.transitions = ["fade", "fade", "fade", "fade"]


        self.bg_music_path = os.path.join(self.music_dir, "bg_track.mp3")


        # Branding.
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


        # Mix documentaire : voix prioritaire, musique réellement en arrière-plan.
        self.voice_gain = 1.08
        self.music_gain = 0.085
        self.music_fade_duration = 2.5
        self.transition_duration = 0.38


        # Sous-titres : plus lisibles sur mobile sans devenir énormes.
        self.subtitle_style = (
            "FontName=DejaVu Sans,"
            "FontSize=24,"
            "Bold=1,"
            "PrimaryColour=&H00FFFFFF,"
            "SecondaryColour=&H00FFFFFF,"
            "OutlineColour=&H00000000,"
            "BackColour=&H78000000,"
            "BorderStyle=3,"
            "Outline=1.5,"
            "Shadow=0,"
            "Alignment=2,"
            "MarginL=70,"
            "MarginR=70,"
            "MarginV=125"
        )


        # Crédit discret des sources visuelles.
        self.source_credit_y = "h-520"
        self.source_credit_size = 18
        self.source_credit_alpha = 0.52


        # Police conservée comme fallback éventuel pour du texte branding.
        self.watermark_font_path = (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        )


        # === CORRECTIF : mapping explicite source_type -> texte credit ===
        # Aligne enfin la detection sur les vraies valeurs retournees par
        # AssetManager.get_best_asset() ("wiki", "openverse", "video", "ai"),
        # utilisees par main.py pour nommer les fichiers
        # (scene_{source_type}_{scene_id}.mp4). Avant ce correctif,
        # "openverse" ne matchait aucune condition et retombait sur le
        # libelle generique "Illustration", ce qui rendait le credit
        # incorrect pour toutes les images trouvees via Openverse.
        #
        # AJOUT MODE_HOLOGRAM : "hologram" est le source_type utilise par
        # main.py pour les scenes rendues via
        # modules/visuals/scene_map_hologram.py (cartes wireframe
        # OSMnx + Manim), afin d'afficher un credit coherent plutot que
        # le libelle generique "Illustration".
        self.source_credit_labels = {
            "wiki": "Source : Wikimedia Commons",
            "wikimedia": "Source : Wikimedia Commons",
            "openverse": "Source : Openverse",
            "video": "Illustration : Pexels / Pixabay",
            "pexels": "Illustration : Pexels / Pixabay",
            "pixabay": "Illustration : Pexels / Pixabay",
            "videvo": "Illustration : Pexels / Pixabay",
            "ai": "Illustration générée par IA",
            "hologram": "Carte générée : OpenStreetMap",
        }


    # ------------------------------------------------------------------
    # Utilitaires
    # ------------------------------------------------------------------


    def get_duration(self, filepath):
        try:
            probe = ffmpeg.probe(filepath)
            return float(probe["format"]["duration"])
        except Exception:
            return 0.0


    def _escape_path_for_filter(self, path):
        escaped = str(path).replace("\\\\", "/")
        escaped = escaped.replace(":", "\\\\:")
        escaped = escaped.replace("'", r"\\'")
        return escaped


    def _escape_drawtext(self, text):
        """
        Echappe les caractères sensibles pour drawtext.
        """
        return (
            str(text)
            .replace("\\\\", r"\\\\")
            .replace(":", r"\\:")
            .replace("'", r"\\'")
            .replace(",", r"\\,")
        )


    def _ensure_pair(self, image_pair):
        if isinstance(image_pair, dict):
            path_a = image_pair.get("a")
            path_b = image_pair.get("b", path_a)
            return path_a, path_b


        if isinstance(image_pair, (list, tuple)) and len(image_pair) >= 2:
            return image_pair[0], image_pair[1]


        if image_pair:
            return str(image_pair), str(image_pair)


        return None, None


    def _is_video_file(self, path):
        return str(path).lower().endswith(
            (".mp4", ".mov", ".webm", ".avi", ".mkv", ".m4v")
        )


    def _resolve_source_credit(self, path_a):
        """
        CORRECTIF : detection du credit de source basee sur le
        source_type explicite injecte dans le nom de fichier par
        main.py ("scene_{source_type}_{scene_id}.mp4"), avec fallback
        sur l'ancienne heuristique par mots-cles pour compatibilite si
        jamais un fichier ne suit pas cette convention de nommage.
        """
        file_name = str(path_a).lower()


        # 1. Detection exacte via le token source_type present dans le nom
        for token, label in self.source_credit_labels.items():
            if f"_{token}_" in file_name or file_name.startswith(f"{token}_"):
                return label


        # 2. Fallback heuristique (ancien comportement, compatibilite)
        if "wiki" in file_name or "wikimedia" in file_name:
            return "Source : Wikimedia Commons"
        if "openverse" in file_name:
            return "Source : Openverse"
        if any(token in file_name for token in ("pexels", "pixabay", "videvo", "video")):
            return "Illustration : Pexels / Pixabay"
        if any(token in file_name for token in ("generated", "ai_", "midjourney", "gemini", "_ai_")):
            return "Illustration générée par IA"
        if "hologram" in file_name:
            return "Carte générée : OpenStreetMap"


        return "Illustration"


    # ------------------------------------------------------------------
    # FILIGRANE PREMIUM
    # ------------------------------------------------------------------


    def add_watermark(self, input_video_path, output_video_path):
        """
        Ajoute le logo Minute Mystère en haut à gauche.


        Le PNG doit idéalement avoir un fond transparent.
        Le logo est volontairement petit et discret : il signe la vidéo
        sans concurrencer les sous-titres ni la narration.
        """
        if not os.path.exists(self.watermark_path):
            print(
                f"⚠️ Filigrane introuvable : {self.watermark_path}"
            )
            return False


        try:
            video = ffmpeg.input(input_video_path)


            logo = ffmpeg.input(
                self.watermark_path,
                loop=1,
                framerate=self.fps
            ).video


            logo = (
                logo
                .filter(
                    "scale",
                    self.watermark_width,
                    -1,
                    force_original_aspect_ratio="decrease"
                )
                .filter("format", "rgba")
                .filter("colorchannelmixer", aa=self.watermark_opacity)
            )


            watermarked_video = ffmpeg.overlay(
                video.video,
                logo,
                x=self.watermark_x,
                y=self.watermark_y,
                eof_action="repeat",
                shortest=1
            )


            runner = ffmpeg.output(
                watermarked_video,
                video.audio,
                output_video_path,
                vcodec="libx264",
                acodec="aac",
                audio_bitrate="192k",
                pix_fmt="yuv420p",
                r=self.fps,
                crf=18,
                preset="medium",
                movflags="faststart",
                shortest=None
            )


            runner.run(overwrite_output=True, quiet=True)


            if os.path.exists(output_video_path):
                print(
                    f"      Filigrane Minute Mystère ajouté "
                    f"({self.watermark_width}px, opacity={self.watermark_opacity:.2f})"
                )
                return True


            return False


        except ffmpeg.Error as e:
            error_log = (
                e.stderr.decode("utf8", errors="ignore")
                if e.stderr
                else str(e)
            )
            print(f"⚠️ Watermark failed: {error_log}")
            return False


        except Exception as e:
            print(f"⚠️ Watermark failed: {e}")
            return False


    def add_watermark_text(
        self,
        input_video_path,
        output_video_path,
        channel_name="@MinuteMystere"
    ):
        print(
            "      add_watermark_text() est conservé pour compatibilité : "
            "utilisation du logo Minute Mystère."
        )
        return self.add_watermark(
            input_video_path,
            output_video_path
        )


    # ------------------------------------------------------------------
    # RENDU D'UNE SCÈNE
    # ------------------------------------------------------------------


    def process_scene(
        self,
        scene,
        image_pair,
        bg_video_path=None,
        bg_offset=0.0
    ):
        scene_id = scene["id"]
        audio_path = scene["audio_path"]
        total_duration = float(scene["duration"])


        output_path = os.path.join(
            self.temp_dir,
            f"scene_{scene_id}_rendered.mp4"
        )


        path_a = None
        path_b = None


        try:
            input_audio = ffmpeg.input(audio_path)


            if bg_video_path and os.path.exists(bg_video_path):
                source_duration = self.get_duration(bg_video_path)
                start_offset = (
                    bg_offset % source_duration
                    if source_duration > 0
                    else 0.0
                )


                video_stream = (
                    ffmpeg.input(
                        bg_video_path,
                        stream_loop=-1,
                        ss=start_offset
                    )
                    .filter("trim", duration=total_duration)
                    .filter(
                        "scale",
                        self.video_width,
                        self.video_height,
                        force_original_aspect_ratio="increase"
                    )
                    .filter(
                        "crop",
                        self.video_width,
                        self.video_height
                    )
                    .setpts("PTS-STARTPTS")
                )


            else:
                path_a, path_b = self._ensure_pair(image_pair)


                if not path_a:
                    raise ValueError(
                        f"Scene {scene_id}: aucune image ou vidéo disponible."
                    )


                path_b = path_b or path_a


                if self._is_video_file(path_a):
                    video_stream = (
                        ffmpeg.input(
                            path_a,
                            stream_loop=-1
                        )
                        .filter("trim", duration=total_duration)
                        .filter(
                            "scale",
                            self.video_width,
                            self.video_height,
                            force_original_aspect_ratio="increase"
                        )
                        .filter(
                            "crop",
                            self.video_width,
                            self.video_height
                        )
                        .setpts("PTS-STARTPTS")
                    )


                else:
                    duration_a = max(total_duration / 2, 0.1)
                    duration_b = max(
                        (total_duration / 2) + 0.35,
                        0.1
                    )


                    frames_a = max(
                        int(duration_a * self.fps),
                        1
                    )
                    frames_b = max(
                        int(duration_b * self.fps),
                        1
                    )


                    stream_a = (
                        ffmpeg.input(
                            path_a,
                            loop=1,
                            t=duration_a
                        )
                        .filter("scale", 2200, -1)
                        .filter(
                            "zoompan",
                            z="min(zoom+0.0009,1.14)",
                            d=frames_a,
                            s=f"{self.video_width}x{self.video_height}",
                            fps=self.fps
                        )
                        .setpts("PTS-STARTPTS")
                    )


                    stream_b = (
                        ffmpeg.input(
                            path_b,
                            loop=1,
                            t=duration_b
                        )
                        .filter("scale", 2200, -1)
                        .filter(
                            "zoompan",
                            z="if(eq(on,1),1.07,max(zoom-0.0008,1.0))",
                            d=frames_b,
                            s=f"{self.video_width}x{self.video_height}",
                            fps=self.fps
                        )
                        .setpts("PTS-STARTPTS")
                    )


                    video_stream = ffmpeg.concat(
                        stream_a,
                        stream_b,
                        v=1,
                        a=0
                    )


            # ==========================================================
            # 📌 AJOUT DU CRÉDIT DE LA SOURCE (CORRIGÉ)
            # ==========================================================
            source_text = ""


            if not bg_video_path and path_a:
                source_text = self._resolve_source_credit(path_a)


            if source_text:
                video_stream = video_stream.filter(
                    "drawtext",
                    text=self._escape_drawtext(source_text),
                    fontfile=self.watermark_font_path,
                    fontcolor=f"white@{self.source_credit_alpha}",
                    fontsize=self.source_credit_size,
                    box=0,
                    shadowcolor="black@0.75",
                    shadowx=1,
                    shadowy=1,
                    x="30",
                    y=self.source_credit_y
                )


            # ----------------------------------------------------------
            # Sous-titres
            # ----------------------------------------------------------
            srt_path = scene.get("srt_path")


            if srt_path and os.path.exists(srt_path):
                escaped_srt_path = self._escape_path_for_filter(srt_path)


                video_stream = video_stream.filter(
                    "subtitles",
                    filename=escaped_srt_path,
                    force_style=self.subtitle_style
                )


            # ----------------------------------------------------------
            # Encodage scène
            # ----------------------------------------------------------
            runner = ffmpeg.output(
                video_stream,
                input_audio,
                output_path,
                vcodec="libx264",
                acodec="aac",
                audio_bitrate="192k",
                pix_fmt="yuv420p",
                r=self.fps,
                crf=18,
                preset="medium",
                movflags="faststart",
                shortest=None
            )


            runner.run(overwrite_output=True, quiet=True)


            return output_path


        except ffmpeg.Error as e:
            error = (
                e.stderr.decode("utf8", errors="ignore")
                if e.stderr
                else str(e)
            )
            print(
                f"❌ Render Fail Scene {scene_id}: {error}"
            )
            return None


        except Exception as e:
            print(
                f"❌ Render Fail Scene {scene_id}: {e}"
            )
            return None


    # ------------------------------------------------------------------
    # RENDU DE TOUTES LES SCÈNES
    # ------------------------------------------------------------------


    def render_all_scenes(
        self,
        script_data,
        video_pairs,
        bg_video_path=None
    ):
        rendered_paths = []
        bg_cursor = 0.0


        for i, scene in enumerate(script_data):
            current_pair = (
                video_pairs[i]
                if i < len(video_pairs)
                else None
            )


            output_path = self.process_scene(
                scene,
                current_pair,
                bg_video_path=bg_video_path,
                bg_offset=bg_cursor
            )


            bg_cursor += float(scene["duration"])


            if output_path:
                rendered_paths.append(output_path)


        return rendered_paths


    # ------------------------------------------------------------------
    # ASSEMBLAGE
    # ------------------------------------------------------------------


    def _merge_two_clips(
        self,
        clip_a,
        clip_b,
        output_path,
        trans_dur=None
    ):
        trans_dur = (
            trans_dur
            if trans_dur is not None
            else self.transition_duration
        )


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
            audio_bitrate="192k",
            pix_fmt="yuv420p",
            crf=18,
            preset="medium",
            movflags="faststart"
        )


        runner.run(overwrite_output=True, quiet=True)


        return effect, offset


    # ------------------------------------------------------------------
    # NORMALISATION AUDIO
    # ------------------------------------------------------------------


    def _normalize_audio_track(
        self,
        input_video_path,
        output_video_path
    ):
        try:
            src = ffmpeg.input(input_video_path)


            normalized_audio = (
                src.audio
                .filter(
                    "loudnorm",
                    I=-16,
                    TP=-1.5,
                    LRA=9
                )
            )


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
            error_log = (
                e.stderr.decode("utf8", errors="ignore")
                if e.stderr
                else str(e)
            )
            print(f"⚠️ Loudnorm failed: {error_log}")
            return False


    # ------------------------------------------------------------------
    # MUSIQUE + DUCKING
    # ------------------------------------------------------------------


    def _mix_background_music(
        self,
        stitched_path,
        output_path
    ):
        try:
            video_duration = self.get_duration(stitched_path)


            if video_duration <= 0:
                raise ValueError(
                    "Durée vidéo invalide pour le mix audio."
                )


            fade_start = max(
                video_duration - self.music_fade_duration,
                0
            )


            voice = ffmpeg.input(stitched_path)
            music = ffmpeg.input(
                self.bg_music_path,
                stream_loop=-1
            )


            voice_audio = (
                voice.audio
                .filter(
                    "aformat",
                    sample_fmts="fltp",
                    sample_rates=48000,
                    channel_layouts="stereo"
                )
                .filter("volume", self.voice_gain)
                .filter("atrim", duration=video_duration)
                .filter("asetpts", "PTS-STARTPTS")
            )


            music_audio = (
                music.audio
                .filter(
                    "aformat",
                    sample_fmts="fltp",
                    sample_rates=48000,
                    channel_layouts="stereo"
                )
                .filter("volume", self.music_gain)
                .filter("atrim", duration=video_duration)
                .filter("asetpts", "PTS-STARTPTS")
                .filter(
                    "afade",
                    type="in",
                    start_time=0,
                    duration=min(1.2, video_duration)
                )
                .filter(
                    "afade",
                    type="out",
                    start_time=fade_start,
                    duration=self.music_fade_duration
                )
            )


            voice_split = voice_audio.filter_multi_output(
                "asplit",
                2
            )
            voice_for_duck = voice_split[0]
            voice_for_mix = voice_split[1]


            music_split = music_audio.filter_multi_output(
                "asplit",
                2
            )
            music_for_duck = music_split[0]
            music_for_mix = music_split[1]


            ducked_music = ffmpeg.filter(
                [music_for_duck, voice_for_duck],
                "sidechaincompress",
                threshold=0.035,
                ratio=5,
                attack=30,
                release=450,
                makeup=1
            )


            mixed_audio = (
                ffmpeg.filter(
                    [voice_for_mix, ducked_music],
                    "amix",
                    inputs=2,
                    duration="first",
                    dropout_transition=2,
                    normalize=0
                )
                .filter(
                    "loudnorm",
                    I=-16,
                    TP=-1.5,
                    LRA=9
                )
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


            final_runner.run(
                overwrite_output=True,
                quiet=True
            )


            return True


        except ffmpeg.Error as e:
            error_log = (
                e.stderr.decode("utf8", errors="ignore")
                if e.stderr
                else str(e)
            )
            print(
                "⚠️ Music mix failed, falling back to "
                f"no-music version: {error_log}"
            )
            return False


        except Exception as e:
            print(
                "⚠️ Music mix failed, falling back to "
                f"no-music version: {e}"
            )
            return False


    # ------------------------------------------------------------------
    # FINALISATION
    # ------------------------------------------------------------------


    def concatenate_with_transitions(
        self,
        video_paths,
        output_filename="final_short.mp4"
    ):
        raw_final_output_path = os.path.join(
            self.temp_dir,
            "raw_final_stitched.mp4"
        )


        output_path = os.path.join(
            self.final_dir,
            output_filename
        )


        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except Exception:
                pass


        if not video_paths:
            return None


        merge_step_files = []


        if len(video_paths) == 1:
            stitched_path = video_paths[0]


        else:
            courant = video_paths[0]


            for i in range(1, len(video_paths)):
                suivant = video_paths[i]


                merge_output = os.path.join(
                    self.temp_dir,
                    f"merge_step_{i}.mp4"
                )


                try:
                    effect, offset = self._merge_two_clips(
                        courant,
                        suivant,
                        merge_output
                    )


                    print(
                        f"      Transition {i}: {effect} "
                        f"(offset={offset:.2f}s)"
                    )


                except ffmpeg.Error as e:
                    error_log = (
                        e.stderr.decode("utf8", errors="ignore")
                        if e.stderr
                        else str(e)
                    )


                    print(
                        f"❌ Stitching Error at step {i}: "
                        f"{error_log}"
                    )


                    self._cleanup_temp_files(
                        merge_step_files
                    )
                    return None


                if courant.startswith(
                    os.path.join(
                        self.temp_dir,
                        "merge_step_"
                    )
                ):
                    merge_step_files.append(courant)


                courant = merge_output


            stitched_path = courant


        if os.path.exists(self.bg_music_path):
            success = self._mix_background_music(
                stitched_path,
                raw_final_output_path
            )


            if not success:
                normalized_fallback = os.path.join(
                    self.temp_dir,
                    "normalized_no_music.mp4"
                )


                ok = self._normalize_audio_track(
                    stitched_path,
                    normalized_fallback
                )


                if ok and os.path.exists(
                    normalized_fallback
                ):
                    os.replace(
                        normalized_fallback,
                        raw_final_output_path
                    )
                else:
                    shutil.copy2(
                        stitched_path,
                        raw_final_output_path
                    )


        else:
            normalized_fallback = os.path.join(
                self.temp_dir,
                "normalized_no_music.mp4"
            )


            ok = self._normalize_audio_track(
                stitched_path,
                normalized_fallback
            )


            if ok and os.path.exists(
                normalized_fallback
            ):
                os.replace(
                    normalized_fallback,
                    raw_final_output_path
                )
            else:
                shutil.copy2(
                    stitched_path,
                    raw_final_output_path
                )


        watermark_success = self.add_watermark(
            raw_final_output_path,
            output_path
        )


        if not watermark_success:
            print(
                "      ⚠️ Filigrane non appliqué : "
                "copie de la vidéo sans watermark."
            )
            shutil.copy2(
                raw_final_output_path,
                output_path
            )


        if os.path.exists(raw_final_output_path):
            try:
                os.remove(raw_final_output_path)
            except Exception:
                pass


        self._cleanup_temp_files(
            video_paths + merge_step_files,
            keep=output_path
        )


        if (
            stitched_path not in video_paths
            and stitched_path != output_path
        ):
            self._cleanup_temp_files(
                [stitched_path],
                keep=output_path
            )


        return output_path


    # ------------------------------------------------------------------
    # NETTOYAGE
    # ------------------------------------------------------------------


    def _cleanup_temp_files(
        self,
        filepaths,
        keep=None
    ):
        for filepath in filepaths:
            if not filepath or filepath == keep:
                continue


            if os.path.exists(filepath):
                try:
                    os.remove(filepath)
                except Exception:
                    pass
