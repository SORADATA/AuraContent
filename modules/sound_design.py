import os
import random
import subprocess
import time
import ffmpeg


class SoundDesigner:

    def __init__(self, sfx_timeout=120):
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

        # Timeout dur (secondes) pour l'application d'un effet sonore.
        # Même faille que l'ancien composer.py : output.run(quiet=True)
        # n'a pas de timeout et ne logue rien avant/après l'appel, donc
        # un blocage ffmpeg ici serait tout aussi silencieux et invisible
        # dans les logs CI.
        self.sfx_timeout = sfx_timeout

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

    def _run(self, runner, label):
        """
        Exécute un graphe ffmpeg-python avec timeout dur + logs de
        progression, sur le même modèle que Composer._run().
        """
        args = runner.compile(overwrite_output=True)
        t0 = time.time()
        print(f"      ⏳ [SFX] {label} démarré (timeout={self.sfx_timeout}s)...", flush=True)
        try:
            result = subprocess.run(
                args,
                timeout=self.sfx_timeout,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except subprocess.TimeoutExpired:
            elapsed = time.time() - t0
            print(f"      ⏱️ [SFX] {label} TIMEOUT après {elapsed:.1f}s.", flush=True)
            raise TimeoutError(f"{label}: timeout après {self.sfx_timeout}s")

        elapsed = time.time() - t0
        if result.returncode != 0:
            stderr_text = result.stderr.decode("utf8", errors="ignore") if result.stderr else ""
            print(f"      ❌ [SFX] {label} échec ffmpeg (code {result.returncode}) en {elapsed:.1f}s", flush=True)
            raise ffmpeg.Error("ffmpeg", result.stdout, result.stderr)

        print(f"      ✅ [SFX] {label} terminé en {elapsed:.1f}s", flush=True)
        return result

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
            print(f"      ⚠️ [SFX] Aucun fichier trouvé pour l'effet '{effect_name}', ignoré.", flush=True)
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

            self._run(output, label=f"application effet '{effect_name}'")

            return os.path.exists(
                output_path
            )

        except TimeoutError as exc:
            print(f"⚠️ SFX timeout: {exc}", flush=True)
            return False
        except ffmpeg.Error as exc:
            stderr = getattr(exc, "stderr", None)
            msg = stderr.decode("utf8", errors="ignore") if stderr else str(exc)
            print(f"⚠️ SFX failed: {msg}", flush=True)
            return False
        except Exception as exc:
            print(
                f"⚠️ SFX failed: {exc}",
                flush=True,
            )
            return False
