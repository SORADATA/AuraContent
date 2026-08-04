import os
import random
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

        # MODIFICATION ICI : Style de sous-titres dynamique type Reels/TikTok
        self.subtitle_style = (
            "FontName=Montserrat,"
            "FontSize=26,"
            "PrimaryColour=&H0000FFFF,"      # Jaune vif (très accrocheur)
            "OutlineColour=&H00000000,"      # Contour noir
            "BackColour=&H80000000,"         # Fond semi-transparent
            "BorderStyle=1,"
            "Outline=2,"
            "Shadow=1,"
            "Alignment=2,"
            "MarginV=120"
        )

    def get_duration(self, filepath):
        try:
            probe = ffmpeg.probe(filepath)
            return float(probe["format"]["duration"])
        except Exception:
            return 0.0

    def process_scene(self, scene, image_pair):
        scene_id = scene["id"]
        audio_path = scene["audio_path"]
        total_duration = float(scene["duration"])
        output_path = os.path.join(self.temp_dir, f"scene_{scene_id}.mp4")

        try:
            input_audio = ffmpeg.input(audio_path)

            print(f"    ⚙️ Processing Scene {scene_id}: 🎨 AI Images + Ken Burns Zoom")

            if isinstance(image_pair, dict):
                path_a = image_pair.get("a")
                path_b = image_pair.get("b", path_a)
            elif isinstance(image_pair, (list, tuple)) and len(image_pair) >= 2:
                path_a, path_b = image_pair[0], image_pair[1]
            else:
                path_a = path_b = str(image_pair)

            duration_a = max(total_duration / 2, 0.1)
            duration_b = max((total_duration / 2) + 0.35, 0.1)

            frames_a = max(int(duration_a * self.fps), 1)
            frames_b = max(int(duration_b * self.fps), 1)

            stream_a = (
                ffmpeg
                .input(path_a, loop=1, t=duration_a)
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
                ffmpeg
                .input(path_b, loop=1, t=duration_b)
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

            srt_path = scene.get("srt_path")
            if srt_path and os.path.exists(srt_path):
                video_stream = video_stream.filter(
                    "subtitles",
                    filename=srt_path,
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

    def render_all_scenes(self, script_data, video_pairs):
        rendered_paths = []

        for i, scene in enumerate(script_data):
            current_pair = video_pairs[i]
            if current_pair is None:
                continue

            output_path = self.process_scene(scene, current_pair)
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
        """
        Mixe la voix et la musique avec ducking automatique.
        Version corrigee pour ffmpeg-python avec duplication explicite
        des flux reutilises dans plusieurs branches.
        """
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

            # Duplication explicite des flux reutilises
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

    def concatenate_with_transitions(self, video_paths, output_filename="final_short.mp4"):
        print("🎬 Stitching final video (cascade mode)...")
        output_path = os.path.join(self.final_dir, output_filename)

        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except Exception:
                print(f"⚠️ Warning: Could not delete old file {output_path}.")

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
                    error_log = e.stderr.decode("utf8") if e.stderr else str(e)
                    print(f"❌ Stitching Error at step {i}: {error_log}")
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
                print("🔈 Fallback: export sans musique, avec normalisation voix...")
                ok = self._normalize_audio_track(stitched_path, normalized_fallback)

                if ok and os.path.exists(normalized_fallback):
                    os.replace(normalized_fallback, output_path)
                else:
                    os.replace(stitched_path, output_path)
        else:
            print("⚠️ Aucune musique de fond trouvee dans assets/music/bg_track.mp3, export avec voix normalisee.")
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

        return output_path
