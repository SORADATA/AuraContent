
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
        self.music_volume = 0.08
        self.music_fade_duration = 1.5

    def get_duration(self, filepath):
        try:
            probe = ffmpeg.probe(filepath)
            return float(probe["format"]["duration"])
        except Exception:
            return 0.0

    def process_scene(self, scene, image_pair):
        scene_id = scene["id"]
        audio_path = scene["audio_path"]
        total_duration = scene["duration"]
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

            duration_a = total_duration / 2
            duration_b = (total_duration / 2) + 0.5

            frames_a = int(duration_a * 30)
            frames_b = int(duration_b * 30)

            stream_a = (
                ffmpeg.input(path_a, loop=1, t=duration_a)
                .filter("scale", 2000, -1)
                .filter("zoompan", z="min(zoom+0.0015,1.3)", d=frames_a, s="1080x1920", fps=30)
                .setpts("PTS-STARTPTS")
            )

            stream_b = (
                ffmpeg.input(path_b, loop=1, t=duration_b)
                .filter("scale", 2000, -1)
                .filter("zoompan", z="if(eq(on,1),1.2,max(zoom-0.0015,1.0))", d=frames_b, s="1080x1920", fps=30)
                .setpts("PTS-STARTPTS")
            )

            video_stream = ffmpeg.concat(stream_a, stream_b, v=1, a=0)

            srt_path = scene.get("srt_path")
            if srt_path and os.path.exists(srt_path):
                video_stream = video_stream.filter(
                    "subtitles",
                    filename=srt_path,
                    force_style="FontName=Arial Black,FontSize=16,PrimaryColour=&HFFFFFF,OutlineColour=&H000000,BorderStyle=3,Outline=2,Alignment=2,MarginV=120"
                )

            runner = ffmpeg.output(
                video_stream,
                input_audio,
                output_path,
                vcodec="libx264",
                acodec="aac",
                pix_fmt="yuv420p",
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

    def _merge_two_clips(self, clip_a, clip_b, output_path, trans_dur=0.5):
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

    def _mix_background_music(self, stitched_path, output_path):
        """
        Mixe la musique de fond (en boucle) avec la piste voix/video deja stitchee.
        Applique un volume reduit et un fade-out en fin de piste pour eviter
        une coupure brusque. Retourne True si le mix a reussi, False sinon
        (l'appelant doit alors faire un fallback vers la version sans musique).
        """
        try:
            video_duration = self.get_duration(stitched_path)
            fade_start = max(video_duration - self.music_fade_duration, 0)

            voice = ffmpeg.input(stitched_path)
            music = ffmpeg.input(self.bg_music_path, stream_loop=-1)

            music_audio = (
                music.audio
                .filter("volume", self.music_volume)
                .filter("afade", type="out", start_time=fade_start, duration=self.music_fade_duration)
            )

            mixed_audio = ffmpeg.filter(
                [voice.audio, music_audio], "amix", duration="first", dropout_transition=2
            )

            final_runner = ffmpeg.output(
                voice.video,
                mixed_audio,
                output_path,
                vcodec="libx264",
                acodec="aac",
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
            print("🎵 Mixing background music...")
            success = self._mix_background_music(stitched_path, output_path)
            if not success:
                os.replace(stitched_path, output_path)
        else:
            print("⚠️ Aucune musique de fond trouvee dans assets/music/bg_track.mp3, export sans musique.")
            os.replace(stitched_path, output_path)
            print(f"✅ FINAL VIDEO SAVED: {output_path}")

        if stitched_path != output_path and os.path.exists(stitched_path):
            try:
                os.remove(stitched_path)
            except Exception:
                pass

        return output_path
