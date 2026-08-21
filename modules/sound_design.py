import os
import random
import ffmpeg


class SoundDesigner:

    def __init__(self):
        self.sfx_dir = os.path.join(
            os.getcwd(),
            "assets",
            "sfx"
        )

        os.makedirs(
            self.sfx_dir,
            exist_ok=True
        )

        self.default_gain = 0.18

    def find_sfx(self, effect_name):
        if not effect_name:
            return None

        extensions = (
            ".mp3",
            ".wav",
            ".m4a",
            ".ogg"
        )

        candidates = [
            os.path.join(
                self.sfx_dir,
                effect_name + ext
            )
            for ext in extensions
        ]

        existing = [
            path for path in candidates
            if os.path.exists(path)
        ]

        if not existing:
            return None

        return random.choice(existing)

    def apply_effect(
        self,
        video_path,
        output_path,
        effect_name,
        start_time=0.0,
        volume=None
    ):
        sfx_path = self.find_sfx(
            effect_name
        )

        if not sfx_path:
            return False

        volume = (
            self.default_gain
            if volume is None
            else volume
        )

        try:
            video = ffmpeg.input(
                video_path
            )

            sfx = (
                ffmpeg.input(
                    sfx_path
                )
                .audio
                .filter(
                    "volume",
                    volume
                )
                .filter(
                    "adelay",
                    f"{int(start_time * 1000)}|"
                    f"{int(start_time * 1000)}"
                )
            )

            mixed = ffmpeg.filter(
                [
                    video.audio,
                    sfx
                ],
                "amix",
                inputs=2,
                duration="first",
                dropout_transition=1,
                normalize=0
            )

            output = ffmpeg.output(
                video.video,
                mixed,
                output_path,
                vcodec="copy",
                acodec="aac",
                audio_bitrate="192k",
                movflags="faststart"
            )

            output.run(
                overwrite_output=True,
                quiet=True
            )

            return os.path.exists(
                output_path
            )

        except Exception as exc:
            print(
                f"⚠️ SFX failed: {exc}"
            )
            return False