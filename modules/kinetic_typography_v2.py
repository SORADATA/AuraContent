import os
import math
import textwrap
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

    def _split_text(self, text, max_chars=42):
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
        after = " ".join(words[idx + 1 :]).strip()
        return before, keyword, after

    def _draw_gradient_bg(self, duration, palette):
        return ffmpeg.input(
            f"color=c={palette['bg1']}:s={self.width}x{self.height}:d={duration}:r={self.fps}",
            f="lavfi",
        ).video.filter(
            "gradients",
            s=f"{self.width}x{self.height}",
            c0=palette["bg1"],
            c1=palette["bg2"],
            x0=0,
            y0=0,
            x1=self.width,
            y1=self.height,
            d=duration,
            rate=self.fps,
        )

    def generate(self, scene, duration, output_path):
        text = scene.get("text", "")
        mood = scene.get("mood", "pedagogical")
        emphasis_word = scene.get("tts_emphasis_word")
        palette = PALETTE_BY_MOOD.get(mood, DEFAULT_PALETTE)

        before, keyword, after = self._split_around_emphasis(text, emphasis_word)

        base = ffmpeg.input(
            f"gradients=s={self.width}x{self.height}:c0={palette['bg1']}:c1={palette['bg2']}:"
            f"x0=0:y0=0:x1={self.width}:y1={self.height}:d={duration}:rate={self.fps}",
            f="lavfi",
        )

        video_stream = base.video
        anim_in = 0.35
        slide_x = f"if(lt(t,{anim_in}),(w-text_w)/2-60+60*(t/{anim_in}),(w-text_w)/2)"
        fade_alpha = f"if(lt(t,{anim_in}),t/{anim_in},1)"

        if keyword:
            before_lines = self._split_text(before, 46) if before else []
            after_lines = self._split_text(after, 46) if after else []

            y_top = int(self.height * 0.33)
            y_mid = int(self.height * 0.45)
            y_bottom = int(self.height * 0.57)

            if before_lines:
                video_stream = video_stream.filter(
                    "drawtext",
                    fontfile=self.font_regular,
                    text=self._escape_text("\n".join(before_lines)),
                    fontsize=44,
                    fontcolor="0xE8EDF2",
                    alpha=fade_alpha,
                    x=slide_x,
                    y=y_top,
                    line_spacing=10,
                    box=1,
                    boxcolor="0x000000@0.18",
                    boxborderw=18,
                )

            video_stream = video_stream.filter(
                "drawtext",
                fontfile=self.font_bold,
                text=self._escape_text(keyword.upper()),
                fontsize=84,
                fontcolor=palette["accent"],
                alpha=f"if(lt(t,{anim_in + 0.08}),(t-0.08)/{anim_in},1)",
                x="(w-text_w)/2",
                y=y_mid,
                borderw=2,
                bordercolor="0x000000@0.45",
                box=1,
                boxcolor="0x000000@0.20",
                boxborderw=16,
            )

            if after_lines:
                video_stream = video_stream.filter(
                    "drawtext",
                    fontfile=self.font_regular,
                    text=self._escape_text("\n".join(after_lines)),
                    fontsize=44,
                    fontcolor="0xD9E2EC",
                    alpha=fade_alpha,
                    x=slide_x,
                    y=y_bottom,
                    line_spacing=10,
                    box=1,
                    boxcolor="0x000000@0.18",
                    boxborderw=18,
                )
        else:
            lines = self._split_text(text, 40)
            y_center = int(self.height * 0.43)
            video_stream = video_stream.filter(
                "drawtext",
                fontfile=self.font_bold,
                text=self._escape_text("\n".join(lines)),
                fontsize=58,
                fontcolor="0xE8EDF2",
                alpha=fade_alpha,
                x="(w-text_w)/2",
                y=y_center,
                line_spacing=14,
                box=1,
                boxcolor="0x000000@0.20",
                boxborderw=18,
            )

        progress_h = 6
        video_stream = video_stream.filter(
            "drawbox",
            x=0,
            y=self.height - 12,
            w=self.width,
            h=progress_h,
            color=f"{palette['accent']}@0.22",
            t="fill",
        )
        video_stream = video_stream.filter(
            "drawbox",
            x=0,
            y=self.height - 12,
            w=f"iw*min(t/{duration},1)",
            h=progress_h,
            color=f"{palette['accent']}@0.95",
            t="fill",
        )

        try:
            runner = ffmpeg.output(
                video_stream,
                output_path,
                vcodec="libx264",
                pix_fmt="yuv420p",
                r=60,
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