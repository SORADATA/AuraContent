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

    def concatenate_with_transitions(self, video_paths, output_filename="final_short.mp4"):
        print("🎬 Stitching final video...")
        stitched_path = os.path.join(self.temp_dir, "stitched_no_music.mp4")
        output_path = os.path.join(self.final_dir, output_filename)

        for p in (stitched_path, output_path):
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    print(f"⚠️ Warning: Could not delete old file {p}.")

        if not video_paths:
            return None

        input1 = ffmpeg.input(video_paths[0])
        v_stream = input1.video
        a_stream = input1.audio

        current_dur = self.get_duration(video_paths[0])

        for i in range(1, len(video_paths)):
            next_clip = ffmpeg.input(video_paths[i])
            next_dur = self.get_duration(video_paths[i])

            trans_dur = 0.5
            offset = current_dur - trans_dur

            effect = random.choice(self.transitions)
            print(f"    ✨ Transition {i}: '{effect}' at {offset:.2f}s")

            v_stream = ffmpeg.filter(
                [v_stream, next_clip.video],
                "xfade",
                transition=effect,
                duration=trans_dur,
                offset=offset
            )

            a_stream = ffmpeg.filter(
                [a_stream, next_clip.audio],
                "acrossfade",
                d=trans_dur
            )

            current_dur = (current_dur + next_dur) - trans_dur

        try:
            runner = ffmpeg.output(
                v_stream,
                a_stream,
                stitched_path,
                vcodec="libx264",
                acodec="aac",
                pix_fmt="yuv420p",
                movflags="faststart",
                preset="medium"
            )
            runner.run(overwrite_output=True, quiet=False)
        except ffmpeg.Error as e:
            error_log = e.stderr.decode("utf8") if e.stderr else str(e)
            print(f"❌ Stitching Error: {error_log}")
            return None

        if os.path.exists(self.bg_music_path):
            print("🎵 Mixing background music...")
            try:
                voice = ffmpeg.input(stitched_path)
                music = ffmpeg.input(self.bg_music_path, stream_loop=-1)

                music_audio = music.audio.filter("volume", 0.08)
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
                return output_path
            except ffmpeg.Error as e:
                error_log = e.stderr.decode("utf8") if e.stderr else str(e)
                print(f"⚠️ Music mix failed, falling back to no-music version: {error_log}")
                os.replace(stitched_path, output_path)
                return output_path
        else:
            print("⚠️ Aucune musique de fond trouvee dans assets/music/bg_track.mp3, export sans musique.")
            os.replace(stitched_path, output_path)
            print(f"✅ FINAL VIDEO SAVED: {output_path}")
            return output_path