import json
import os
import subprocess
import time


class QualityControl:

    def __init__(
        self,
        min_duration=15,
        max_duration=90,
        expected_width=1080,
        expected_height=1920,
        probe_timeout=60,
    ):
        self.min_duration = min_duration
        self.max_duration = max_duration
        self.expected_width = expected_width
        self.expected_height = expected_height

        # Timeout dur (secondes) pour l'appel ffprobe. Un fichier vidéo
        # corrompu ou tronqué (ex: rendu précédent tué en plein milieu)
        # peut faire bloquer ffprobe indéfiniment sans lever d'erreur ni
        # rien afficher — ffmpeg.probe() de ffmpeg-python n'a PAS de
        # timeout intégré. On appelle donc ffprobe nous-mêmes via
        # subprocess.run(timeout=...) pour garder le contrôle.
        self.probe_timeout = probe_timeout

    def _probe(self, video_path):
        """
        Remplace ffmpeg.probe() par un appel ffprobe direct avec timeout
        dur, pour éviter tout blocage silencieux sur un fichier corrompu.
        """
        args = [
            "ffprobe",
            "-v", "error",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            video_path,
        ]
        t0 = time.time()
        print(f"      ⏳ [QC] ffprobe démarré (timeout={self.probe_timeout}s)...", flush=True)
        try:
            result = subprocess.run(
                args,
                timeout=self.probe_timeout,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except subprocess.TimeoutExpired:
            elapsed = time.time() - t0
            print(f"      ⏱️ [QC] ffprobe TIMEOUT après {elapsed:.1f}s — probablement un fichier corrompu.", flush=True)
            raise RuntimeError(f"ffprobe timeout après {self.probe_timeout}s sur {video_path}")

        elapsed = time.time() - t0
        if result.returncode != 0:
            stderr_text = result.stderr.decode("utf8", errors="ignore") if result.stderr else ""
            print(f"      ❌ [QC] ffprobe échec (code {result.returncode}) en {elapsed:.1f}s", flush=True)
            raise RuntimeError(f"ffprobe error: {stderr_text}")

        print(f"      ✅ [QC] ffprobe terminé en {elapsed:.1f}s", flush=True)
        return json.loads(result.stdout.decode("utf8", errors="ignore"))

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
            probe = self._probe(video_path)

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
        print("      🔎 [QC] Inspection du fichier final...", flush=True)
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
