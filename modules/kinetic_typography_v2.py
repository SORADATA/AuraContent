import os
import re
import ffmpeg

PALETTE_BY_MOOD = {
    "confident": {"bg1": "0x0B1424", "bg2": "0x152238", "accent": "0x00D9B5"},
    "sharp": {"bg1": "0x140E1F", "bg2": "0x231433", "accent": "0xFF5C5C"},
    "clear": {"bg1": "0x0A1B2A", "bg2": "0x123047", "accent": "0x4CC9F0"},
    "pedagogical": {"bg1": "0x0C1420", "bg2": "0x18293D", "accent": "0xFFC857"},
    "engaging": {"bg1": "0x0D1B2A", "bg2": "0x1B2F4A", "accent": "0x06D6A0"},
    "revelatory": {"bg1": "0x160F26", "bg2": "0x281B3D", "accent": "0xEF476F"},
}
DEFAULT_PALETTE = {"bg1": "0x0E1420", "bg2": "0x1A2438", "accent": "0x4CC9F0"}


class KineticTypographyEngineV2:
    def __init__(self, font_bold=None, font_regular=None, width=1080, height=1920, fps=30):
        fonts_dir = os.path.join(os.getcwd(), "assets", "fonts")
        self.font_bold = font_bold or os.path.join(fonts_dir, "Montserrat-Bold.ttf")
        self.font_regular = font_regular or os.path.join(fonts_dir, "Montserrat-Regular.ttf")
        self.width = width
        self.height = height
        self.fps = fps

        for path in (self.font_bold, self.font_regular):
            if not os.path.exists(path):
                print(f"⚠️ Police manquante : {path}")

    def _escape_text(self, text):
        if text is None:
            return ""
        return (
            str(text)
            .replace("\\", "\\\\")
            .replace(":", "\\:")
            .replace("'", "’")
            .replace("%", "\\%")
            .replace("\n", " ")
        )

    def _split_text(self, text, max_chars=38):
        words = text.split()
        lines = []
        current = []
        for w in words:
            test = " ".join(current + [w])
            if len(test) <= max_chars:
                current.append(w)
            else:
                if current:
                    lines.append(" ".join(current))
                current = [w]
        if current:
            lines.append(" ".join(current))
        return lines

    def _split_around_emphasis(self, text, emphasis_word):
        if not emphasis_word or not text:
            return text, None, ""

        words = text.split()
        target = emphasis_word.strip().lower()
        idx = next((i for i, w in enumerate(words) if target in w.lower()), None)
        if idx is None:
            return text, None, ""

        before = " ".join(words[:idx]).strip()
        keyword = words[idx].strip()
        after = " ".join(words[idx + 1:]).strip()
        return before, keyword, after

    def _build_background(self, duration, palette):
        bg = ffmpeg.input(
            f"color=c={palette['bg1']}:s={self.width}x{self.height}:d={duration}:r={self.fps}",
            f="lavfi",
        ).video

        overlay = ffmpeg.input(
            f"color=c={palette['bg2']}@0.10:s={self.width}x{self.height}:d={duration}:r={self.fps}",
            f="lavfi",
        ).video

        combined = ffmpeg.overlay(bg, overlay, x=0, y=0)

        return (
            combined
            .filter("scale", self.width + 24, self.height + 24)
            .filter("crop", self.width, self.height)
        )

    def generate(self, scene, duration, output_path):
        text = scene.get("text", "")
        mood = scene.get("mood", "pedagogical")
        emphasis_word = scene.get("tts_emphasis_word")
        palette = PALETTE_BY_MOOD.get(mood, DEFAULT_PALETTE)

        before, keyword, after = self._split_around_emphasis(text, emphasis_word)

        video_stream = self._build_background(duration, palette)

        intro = 0.35
        settle = 0.25

        bg_shift_x = f"0.5*sin(2*PI*t/{max(duration, 1) * 3})"
        bg_shift_y = f"0.5*cos(2*PI*t/{max(duration, 1) * 4})"

        video_stream = video_stream.filter(
            "pad",
            self.width + 40,
            self.height + 40,
            20,
            20,
            color=palette["bg1"]
        ).filter(
            "crop",
            f"{self.width}:{self.height}",
            x=f"20+{bg_shift_x}",
            y=f"20+{bg_shift_y}"
        )

        if keyword:
            before_lines = self._split_text(before, 42) if before else []
            after_lines = self._split_text(after, 42) if after else []

            top_y = int(self.height * 0.31)
            mid_y = int(self.height * 0.45)
            bot_y = int(self.height * 0.58)

            slide_in = f"(w-text_w)/2 - 58*(1-min(t/{intro},1))"
            alpha_in = f"if(lt(t,{intro}),t/{intro},1)"
            small_pop = f"1+0.05*sin(min(t/{intro},1)*3.14159)"

            if before_lines:
                video_stream = video_stream.filter(
                    "drawtext",
                    fontfile=self.font_regular,
                    text=self._escape_text("\n".join(before_lines)),
                    fontsize=44,
                    fontcolor="0xE8EDF2",
                    alpha=alpha_in,
                    x=slide_in,
                    y=top_y,
                    line_spacing=10,
                    box=1,
                    boxcolor="0x000000@0.16",
                    boxborderw=18,
                )

            video_stream = video_stream.filter(
                "drawtext",
                fontfile=self.font_bold,
                text=self._escape_text(keyword.upper()),
                fontsize=86,
                fontcolor=palette["accent"],
                alpha=f"if(lt(t,{intro + 0.08}),(t-0.08)/{intro},1)",
                x=f"(w-text_w)/2 + 8*sin(t*2.2)",
                y=mid_y,
                borderw=2,
                bordercolor="0x000000@0.42",
                box=1,
                boxcolor="0x000000@0.18",
                boxborderw=18,
            ).filter(
                "scale",
                f"iw*{small_pop}",
                f"ih*{small_pop}"
            )

            if after_lines:
                video_stream = video_stream.filter(
                    "drawtext",
                    fontfile=self.font_regular,
                    text=self._escape_text("\n".join(after_lines)),
                    fontsize=44,
                    fontcolor="0xD9E2EC",
                    alpha=alpha_in,
                    x=slide_in,
                    y=bot_y,
                    line_spacing=10,
                    box=1,
                    boxcolor="0x000000@0.16",
                    boxborderw=18,
                )
        else:
            lines = self._split_text(text, 40)
            y_center = int(self.height * 0.42)
            video_stream = video_stream.filter(
                "drawtext",
                fontfile=self.font_bold,
                text=self._escape_text("\n".join(lines)),
                fontsize=60,
                fontcolor="0xE8EDF2",
                alpha=f"if(lt(t,{intro}),t/{intro},1)",
                x="(w-text_w)/2 + 6*sin(t*1.8)",
                y=y_center,
                line_spacing=14,
                box=1,
                boxcolor="0x000000@0.18",
                boxborderw=18,
            )

        video_stream = video_stream.filter(
            "drawbox",
            x=0,
            y=self.height - 16,
            w=self.width,
            h=7,
            color=f"{palette['accent']}@0.22",
            t="fill"
        ).filter(
            "drawbox",
            x=0,
            y=self.height - 16,
            w=f"iw*min(t/{duration},1)",
            h=7,
            color=f"{palette['accent']}@0.95",
            t="fill"
        )

        try:
            runner = ffmpeg.output(
                video_stream,
                output_path,
                vcodec="libx264",
                pix_fmt="yuv420p",
                r=self.fps,
                crf=16,
                preset="slow",
                t=duration,
            )
            runner.run(overwrite_output=True, quiet=True)
            return output_path
        except ffmpeg.Error as e:
            error_log = e.stderr.decode("utf8") if e.stderr else str(e)
            print(f"❌ Echec generation kinetic typography v2 : {error_log}")
            return None
