import os
import ffmpeg


class QualityControl:

    def __init__(
        self,
        min_duration=15,
        max_duration=90,
        expected_width=1080,
        expected_height=1920
    ):
        self.min_duration = min_duration
        self.max_duration = max_duration
        self.expected_width = expected_width
        self.expected_height = expected_height

    def inspect(self, video_path):
        report = {
            "valid": False,
            "path": video_path,
            "duration": 0,
            "width": 0,
            "height": 0,
            "fps": 0,
            "has_audio": False,
            "errors": [],
        }

        if not video_path:
            report["errors"].append(
                "Chemin vidéo absent."
            )
            return report

        if not os.path.exists(video_path):
            report["errors"].append(
                "Fichier vidéo absent."
            )
            return report

        if os.path.getsize(video_path) < 10000:
            report["errors"].append(
                "Fichier vidéo trop petit."
            )
            return report

        try:
            probe = ffmpeg.probe(
                video_path
            )

            format_data = probe.get(
                "format",
                {}
            )

            report["duration"] = float(
                format_data.get(
                    "duration",
                    0
                )
            )

            streams = probe.get(
                "streams",
                []
            )

            video_stream = next(
                (
                    s for s in streams
                    if s.get("codec_type") == "video"
                ),
                None
            )

            audio_stream = next(
                (
                    s for s in streams
                    if s.get("codec_type") == "audio"
                ),
                None
            )

            if video_stream:
                report["width"] = int(
                    video_stream.get(
                        "width",
                        0
                    )
                )

                report["height"] = int(
                    video_stream.get(
                        "height",
                        0
                    )
                )

                fps_text = video_stream.get(
                    "r_frame_rate",
                    "0/1"
                )

                try:
                    numerator, denominator = (
                        fps_text.split("/")
                    )

                    report["fps"] = (
                        float(numerator)
                        / max(
                            float(denominator),
                            1
                        )
                    )

                except Exception:
                    report["fps"] = 0

            report["has_audio"] = (
                audio_stream is not None
            )

            if not (
                self.min_duration
                <= report["duration"]
                <= self.max_duration
            ):
                report["errors"].append(
                    f"Durée hors plage : "
                    f"{report['duration']:.2f}s"
                )

            if (
                report["width"]
                != self.expected_width
                or report["height"]
                != self.expected_height
            ):
                report["errors"].append(
                    "Résolution incorrecte : "
                    f"{report['width']}x"
                    f"{report['height']}"
                )

            if not report["has_audio"]:
                report["errors"].append(
                    "Aucune piste audio."
                )

            report["valid"] = (
                len(report["errors"]) == 0
            )

            return report

        except Exception as exc:
            report["errors"].append(
                f"FFprobe error: {exc}"
            )
            return report

    def validate(self, video_path):
        report = self.inspect(
            video_path
        )

        if report["valid"]:
            print(
                "      ✅ QC vidéo : OK "
                f"({report['duration']:.1f}s, "
                f"{report['width']}x"
                f"{report['height']})"
            )
            return True

        print(
            "      ❌ QC vidéo échoué :"
        )

        for error in report["errors"]:
            print(
                f"         - {error}"
            )

        return False