import os
import random
import shutil
import ffmpeg

from modules.utils.karaoke_subtitles import generate_karaoke_subtitles

class Composer:
    def __init__(self):
        self.temp_dir = os.path.join(os.getcwd(), "assets", "temp")
        self.final_dir = os.path.join(os.getcwd(), "assets", "final")
        self.music_dir = os.path.join(os.getcwd(), "assets", "music")

        os.makedirs(self.temp_dir, exist_ok=True)
        os.makedirs(self.final_dir, exist_ok=True)
        os.makedirs(self.music_dir, exist_ok=True)

        self.transitions_by_role = {
            "hook": ["fade", "circleopen", "zoomin"],
            "misconception": ["wipeleft", "wiperight", "slideup"],
            "definition": ["fade", "dissolve"],
            "mechanism": ["slideleft", "slideright", "smoothleft", "smoothright"],
            "analogy": ["circlecrop", "radial", "pixelize"],
            "example": ["wipeup", "wipedown", "distance"],
            "summary": ["fadegrays", "hblur"],
            "cta": ["circleclose", "fadeblack"],
        }
        self.default_transitions = ["fade", "diagbr", "diagtl", "dissolve", "slideup"]
        self.bg_music_path = os.path.join(self.music_dir, "bg_track.mp3")

        self.video_width = 1080
        self.video_height = 1920
        self.fps = 30

        self.voice_gain = 1.15
        self.music_gain = 0.12
        self.music_fade_duration = 1.5
        self.transition_duration = 0.45

        self.subtitle_style = (
            "FontName=Montserrat,"
            "FontSize=26,"
            "PrimaryColour=&H0000FFFF,"
            "OutlineColour=&H00000000,"
            "BackColour=&H80000000,"
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

    def add_watermark_text(self, input_video_path, output_video_path, channel_name="@CapitalSecret"):
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

    def process_scene(self, scene, video_clip_path):
        scene_id = scene["id"]
        audio_path = scene["audio_path"]
        total_duration = float(scene["duration"])
        output_path = os.path.join(self.temp_dir, f"scene_{scene_id}.mp4")

        try:
            input_audio = ffmpeg.input(audio_path)
            print(f"    ⚙️ Processing Scene {scene_id}: assemblage clip + audio + sous-titres")

            video_stream = (
                ffmpeg.input(video_clip_path)
                .filter("scale", self.video_width, self.video_height, force_original_aspect_ratio="increase")
                .filter("crop", self.video_width, self.video_height)
                .filter("setpts", "PTS-STARTPTS")
            )

            ass_path = generate_karaoke_subtitles(audio_path, scene_id, self.temp_dir)
            if ass_path and os.path.exists(ass_path):
                video_stream = video_stream.filter("ass", filename=ass_path)
                print(f"    🎤 Sous-titres karaoke actifs pour scene {scene_id}")
            else:
                srt_path = scene.get("srt_path")
                if srt_path and os.path.exists(srt_path):
                    video_stream = video_stream.filter(
                        "subtitles", filename=srt_path, force_style=self.subtitle_style
                    )
                    print(f"    ⚠️ Fallback sous-titres statiques scene {scene_id}")

            runner = ffmpeg.output(
                video_stream, input_audio, output_path,
                vcodec="libx264", acodec="aac", pix_fmt="yuv420p",
                r=self.fps, crf=18, preset="medium",
                t=total_duration, shortest=None
            )
            runner.run(overwrite_output=True, quiet=True)
            return output_path
        except ffmpeg.Error as e:
            print(f"❌ Render Fail Scene {scene_id}: {e.stderr.decode('utf8') if e.stderr else str(e)}")
            return None

    def render_all_scenes(self, script_data, video_paths):
        rendered_paths = []
        for i, scene in enumerate(script_data):
            current_clip = video_paths[i]
            scene_id = scene["id"]
            audio_path = scene.get("audio_path")

            # --- SÉCURITÉ ANTI-CRASH : Vérification de la durée de l'audio ---
            if audio_path and os.path.exists(audio_path):
                audio_dur = self.get_duration(audio_path)
                if audio_dur < 0.5: # On rejette tout ce qui est < 0.5s
                    print(f"❌ Scene {scene_id} ignorée : audio trop court ({audio_dur:.2f}s), risque de crash FFmpeg.")
                    continue
            
            if current_clip is None or not os.path.exists(current_clip):
                print(f"⚠️ Scene {scene_id}: aucun clip disponible, scene ignoree.")
                continue

            output_path = self.process_scene(scene, current_clip)
            if output_path:
                rendered_paths.append(output_path)
        return rendered_paths

    def _pick_transition(self, scene_role=None):
        pool = self.transitions_by_role.get(scene_role, self.default_transitions)
        return random.choice(pool)

    def _merge_two_clips(self, clip_a, clip_b, output_path, scene_role=None, trans_dur=None):
        trans_dur = trans_dur or self.transition_duration
        dur_a = self.get_duration(clip_a)
        offset = max(dur_a - trans_dur, 0)
        effect = self._pick_transition(scene_role)

        input_a = ffmpeg.input(clip_a)
        input_b = ffmpeg.input(clip_b)

        v_stream = ffmpeg.filter([input_a.video, input_b.video], "xfade",
                                 transition=effect, duration=trans_dur, offset=offset)
        a_stream = ffmpeg.filter([input_a.audio, input_b.audio], "acrossfade", d=trans_dur)

        runner = ffmpeg.output(v_stream, a_stream, output_path,
                               vcodec="libx264", acodec="aac", pix_fmt="yuv420p",
                               crf=18, preset="medium")
        runner.run(overwrite_output=True, quiet=True)
        return effect, offset

    def _normalize_audio_track(self, input_video_path, output_video_path):
        try:
            src = ffmpeg.input(input_video_path)
            normalized_audio = src.audio.filter("loudnorm", I=-16, TP=-1.5, LRA=11)
            runner = ffmpeg.output(src.video, normalized_audio, output_video_path,
                                   vcodec="copy", acodec="aac", audio_bitrate="192k", movflags="faststart")
            runner.run(overwrite_output=True, quiet=True)
            return True
        except ffmpeg.Error as e:
            print(f"⚠️ Loudnorm failed: {e.stderr.decode('utf8') if e.stderr else str(e)}")
            return False

    def _mix_background_music(self, stitched_path, output_path):
        try:
            video_duration = self.get_duration(stitched_path)
            fade_start = max(video_duration - self.music_fade_duration, 0)

            voice = ffmpeg.input(stitched_path)
            music = ffmpeg.input(self.bg_music_path, stream_loop=-1)

            voice_audio_base = (
                voice.audio.filter("aformat", sample_fmts="fltp", sample_rates=48000, channel_layouts="stereo")
                .filter("volume", self.voice_gain).filter("atrim", duration=video_duration)
                .filter("asetpts", "PTS-STARTPTS")
            )
            music_audio_base = (
                music.audio.filter("aformat", sample_fmts="fltp", sample_rates=48000, channel_layouts="stereo")
                .filter("volume", self.music_gain).filter("atrim", duration=video_duration)
                .filter("asetpts", "PTS-STARTPTS")
                .filter("afade", type="out", start_time=fade_start, duration=self.music_fade_duration)
            )

            voice_split = voice_audio_base.filter_multi_output("asplit", 2)
            voice_for_sidechain, voice_for_mix = voice_split[0], voice_split[1]
            music_split = music_audio_base.filter_multi_output("asplit", 2)
            music_for_sidechain, music_for_mix = music_split[0], music_split[1]

            ducked_music = ffmpeg.filter([music_for_sidechain, voice_for_sidechain], "sidechaincompress",
                                         threshold=0.03, ratio=10, attack=20, release=250, makeup=1)
            mixed_audio = (
                ffmpeg.filter([voice_for_mix, ducked_music], "amix", inputs=2,
                              duration="first", dropout_transition=2, normalize=0)
                .filter("loudnorm", I=-16, TP=-1.5, LRA=11)
            )

            final_runner = ffmpeg.output(voice.video, mixed_audio, output_path,
                                         vcodec="libx264", acodec="aac", audio_bitrate="192k",
                                         pix_fmt="yuv420p", movflags="faststart", preset="medium")
            final_runner.run(overwrite_output=True, quiet=False)
            return True
        except ffmpeg.Error as e:
            print(f"⚠️ Music mix failed: {e.stderr.decode('utf8') if e.stderr else str(e)}")
            return False

    def concatenate_with_transitions(self, video_paths, script_data=None, output_filename="final_short.mp4"):
        print("🎬 Stitching final video (cascade mode)...")
        raw_final_output_path = os.path.join(self.temp_dir, "raw_final_stitched.mp4")
        output_path = os.path.join(self.final_dir, output_filename)

        if not video_paths: return None

        if len(video_paths) == 1:
            stitched_path = video_paths[0]
        else:
            courant = video_paths[0]
            for i in range(1, len(video_paths)):
                suivant = video_paths[i]
                merge_output = os.path.join(self.temp_dir, f"merge_step_{i}.mp4")
                scene_role = script_data[i]["role"] if script_data and i < len(script_data) else None
                try:
                    effect, offset = self._merge_two_clips(courant, suivant, merge_output, scene_role=scene_role)
                except ffmpeg.Error:
                    return None
                courant = merge_output
            stitched_path = courant

        if os.path.exists(self.bg_music_path):
            self._mix_background_music(stitched_path, raw_final_output_path)
        else:
            shutil.copy2(stitched_path, raw_final_output_path)

        self.add_watermark_text(raw_final_output_path, output_path, channel_name="@CapitalSecret")
        return output_path
