import os
import random
import shutil
import ffmpeg


class Composer:
    def __init__(self):
        self.temp_dir = os.path.join(os.getcwd(), "assets", "temp")
        self.final_dir = os.path.join(os.getcwd(), "assets", "final")
        self.music_dir = os.path.join(os.getcwd(), "assets", "music")

        os.makedirs(self.temp_dir, exist_ok=True)
        os.makedirs(self.final_dir, exist_ok=True)
        os.makedirs(self.music_dir, exist_ok=True)

        self.transitions = ["fade", "diagbr", "diagtl"]
        self.bg_music_path = os.path.join(self.music_dir, "bg_track.mp3")

        self.video_width = 1080
        self.video_height = 1920
        self.fps = 30

        self.voice_gain = 1.15
        self.music_gain = 0.12
        self.music_fade_duration = 1.5
        self.transition_duration = 0.45

        self.subtitle_style = (
            "FontName=Arial Black,"
            "FontSize=18,"
            "PrimaryColour=&H00FFFFFF,"
            "OutlineColour=&H00000000,"
            "BackColour=&H66000000,"
            "BorderStyle=3,"
            "Outline=2.2,"
            "Shadow=0,"
            "Alignment=2,"
            "MarginV=115"
        )

    def get_duration(self, filepath):
        try:
            probe = ffmpeg.probe(filepath)
            return float(probe["format"]["duration"])
        except Exception:
            return 0.0

    def _escape_path_for_filter(self, path):
        escaped = path.replace("\\", "/")
        escaped = escaped.replace(":", "\\:")
        return escaped

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

    def add_watermark_text(self, input_video_path, output_video_path, channel_name="@MinuteMystere"):
        """Incruste un filigrane texte semi-transparent en bas de la vidéo finale."""
        try:
            stream = ffmpeg.input(input_video_path)
            v_stream = stream.video.filter(
                "drawtext",
                text=channel_name,
                fontcolor="white",
                fontsize=36,
                box=1,
                boxcolor="black@0.5",
                boxborderw=10,
                x="(w-text_w)/2",
                y="h-150"
            )
            a_stream = stream.audio

            runner = ffmpeg.output(
                v_stream,
                a_stream,
                output_video_path,
                vcodec="libx264",
                acodec="copy",
                pix_fmt="yuv420p",
                movflags="faststart"
            )
            runner.run(overwrite_output=True, quiet=True)
            return True
        except ffmpeg.Error as e:
            error_log = e.stderr.decode("utf8") if e.stderr else str(e)
            print(f"⚠️ Watermark failed: {error_log}")
            return False

    def process_scene(self, scene, image_pair, bg_video_path=None, bg_offset=0.0):
        scene_id = scene["id"]
        audio_path = scene["audio_path"]
        total_duration = float(scene["duration"])
        
        # Suffixe _rendered pour éviter les erreurs de verrouillage / écrasement
        output_path = os.path.join(self.temp_dir, f"scene_{scene_id}_rendered.mp4")

        try:
            input_audio = ffmpeg.input(audio_path)

            if bg_video_path and os.path.exists(bg_video_path):
                print(f"    ⚙️ Processing Scene {scene_id}: 🎬 Fond Vidéo Global")

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
                path_a, path_b = self._ensure_pair(image_pair)
                if not path_a:
                    raise ValueError(f"Scene {scene_id}: aucune image ou vidéo disponible.")

                path_b = path_b or path_a

                # Vérification si le fichier fourni est une vidéo ou une image
                is_video = str(path_a).lower().endswith(('.mp4', '.mov', '.webm', '.avi', '.mkv'))

                if is_video:
                    print(f"    ⚙️ Processing Scene {scene_id}: 🎬 Vidéo Stock locale")
                    video_stream = (
                        ffmpeg.input(path_a, stream_loop=-1)
                        .filter("trim", duration=total_duration)
                        .filter("scale", self.video_width, self.video_height, force_original_aspect_ratio="increase")
                        .filter("crop", self.video_width, self.video_height)
                        .setpts("PTS-STARTPTS")
                    )
                else:
                    print(f"    ⚙️ Processing Scene {scene_id}: 🎨 AI Images + Ken Burns Zoom")
                    duration_a = max(total_duration / 2, 0.1)
                    duration_b = max((total_duration / 2) + 0.35, 0.1)

                    frames_a = max(int(duration_a * self.fps), 1)
                    frames_b = max(int(duration_b * self.fps), 1)

                    stream_a = (
                        ffmpeg.input(path_a, loop=1, t=duration_a)
                        .filter("scale", 2200, -1)
                        .filter(
                            "zoompan",
                            z="min(zoom+0.0012,1.18)",
                            d=frames_a,
                            s=f"{self.video_width}x{self.video_height}",
                            fps=self.fps
                        )
                        .setpts("PTS-STARTPTS")
                    )

                    stream_b = (
                        ffmpeg.input(path_b, loop=1, t=duration_b)
                        .filter("scale", 2200, -1)
                        .filter(
                            "zoompan",
                            z="if(eq(on,1),1.10,max(zoom-0.0010,1.0))",
                            d=frames_b,
                            s=f"{self.video_width}x{self.video_height}",
                            fps=self.fps
                        )
                        .setpts("PTS-STARTPTS")
                    )

                    video_stream = ffmpeg.concat(stream_a, stream_b, v=1, a=0)

            # Application des sous-titres
            srt_path = scene.get("srt_path")
            if srt_path and os.path.exists(srt_path):
                escaped_srt_path = self._escape_path_for_filter(srt_path)
                video_stream = video_stream.filter(
                    "subtitles",
                    filename=escaped_srt_path,
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
        except Exception as e:
            print(f"❌ Render Fail Scene {scene_id}: {e}")
            return None

    def render_all_scenes(self, script_data, video_pairs, bg_video_path=None):
        rendered_paths = []
        bg_cursor = 0.0

        for i, scene in enumerate(script_data):
            current_pair = video_pairs[i] if i < len(video_pairs) else None

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

            normalized_audio = src.audio.filter(
                "loudnorm",
                I=-16,
                TP=-1.5,
                LRA=11
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
                ffmpeg.filter(
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
            final_runner.run(overwrite_output=True, quiet=True)
            print(f"✅ FINAL VIDEO SAVED (with music): {output_path}")
            return True

        except ffmpeg.Error as e:
            error_log = e.stderr.decode("utf8") if e.stderr else str(e)
            print(f"⚠️ Music mix failed, falling back to no-music version: {error_log}")
            return False

    def concatenate_with_transitions(self, video_paths, output_filename="final_short.mp4"):
        print("🎬 Stitching final video (cascade mode)...")
        
        # Le fichier final intermédiaire avant d'ajouter le filigrane
        raw_final_output_path = os.path.join(self.temp_dir, "raw_final_stitched.mp4")
        output_path = os.path.join(self.final_dir, output_filename)

        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except Exception:
                print(f"⚠️ Warning: Could not delete old file {output_path}.")

        if not video_paths:
            return None

        merge_step_files = []

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
                    error_log = e.stderr.decode("utf8") if e.stderr else str(e)
                    print(f"❌ Stitching Error at step {i}: {error_log}")
                    self._cleanup_temp_files(merge_step_files)
                    return None

                if courant.startswith(os.path.join(self.temp_dir, "merge_step_")):
                    merge_step_files.append(courant)

                courant = merge_output

            stitched_path = courant

        if os.path.exists(self.bg_music_path):
            print("🎵 Mixing background music with ducking...")
            success = self._mix_background_music(stitched_path, raw_final_output_path)

            if not success:
                normalized_fallback = os.path.join(self.temp_dir, "normalized_no_music.mp4")
                print("🔈 Fallback: export sans musique, avec normalisation voix...")
                ok = self._normalize_audio_track(stitched_path, normalized_fallback)

                if ok and os.path.exists(normalized_fallback):
                    os.replace(normalized_fallback, raw_final_output_path)
                else:
                    shutil.copy2(stitched_path, raw_final_output_path)
        else:
            print("⚠️ Aucune musique de fond trouvée dans assets/music/bg_track.mp3, export avec voix normalisée.")
            normalized_fallback = os.path.join(self.temp_dir, "normalized_no_music.mp4")
            ok = self._normalize_audio_track(stitched_path, normalized_fallback)

            if ok and os.path.exists(normalized_fallback):
                os.replace(normalized_fallback, raw_final_output_path)
            else:
                shutil.copy2(stitched_path, raw_final_output_path)

        # 💧 Application du filigrane textuel sur le fichier final assemblé
        print("💧 Adding watermark text (@MinuteMystere)...")
        watermark_success = self.add_watermark_text(raw_final_output_path, output_path, channel_name="@MinuteMystere")
        
        if not watermark_success:
            print("⚠️ Watermark failed, copying raw final video instead.")
            shutil.copy2(raw_final_output_path, output_path)

        # Nettoyage du fichier intermédiaire brut si besoin
        if os.path.exists(raw_final_output_path):
            try:
                os.remove(raw_final_output_path)
            except Exception:
                pass

        print(f"✅ FINAL VIDEO SAVED (Watermarked): {output_path}")

        self._cleanup_temp_files(video_paths + merge_step_files, keep=output_path)
        if stitched_path not in video_paths and stitched_path != output_path:
            self._cleanup_temp_files([stitched_path], keep=output_path)

        return output_path

    def _cleanup_temp_files(self, filepaths, keep=None):
        for f in filepaths:
            if not f or f == keep:
                continue
            if os.path.exists(f):
                try:
                    os.remove(f)
                except Exception:
                    pass
