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

# --- Tunable constants (kept out of the render logic so styling is easy to adjust) ---
INTRO_DURATION = 0.35          # seconds for the fade/slide-in
KEYWORD_DELAY = 0.08            # keyword appears slightly after the surrounding text
BODY_FONTSIZE = 44
KEYWORD_FONTSIZE_MAX = 86
KEYWORD_FONTSIZE_MIN = 54       # auto-shrink floor for long keywords (e.g. "CAPITALISATION")
SOLO_FONTSIZE = 60
LINE_SPACING = 10
SLIDE_OFFSET_PX = 64
PROGRESS_BAR_HEIGHT = 7
PROGRESS_BAR_MARGIN = 16


class KineticTypographyEngineV2:
    def __init__(self, font_bold=None, font_regular=None, width=1080, height=1920, fps=30):
        fonts_dir = os.path.join(os.getcwd(), "assets", "fonts")
        self.font_bold = font_bold or os.path.join(fonts_dir, "Montserrat-Bold.ttf")
        self.font_regular = font_regular or os.path.join(fonts_dir, "Montserrat-Regular.ttf")
        self.width = width
        self.height = height
        self.fps = fps

        missing = [p for p in (self.font_bold, self.font_regular) if not os.path.exists(p)]
        if missing:
            raise FileNotFoundError(
                "Police(s) manquante(s), impossible de garantir un rendu correct : "
                + ", ".join(missing)
            )

    # ------------------------------------------------------------------
    # Text helpers
    # ------------------------------------------------------------------
    def _escape_text(self, text):
        """Escape for ffmpeg drawtext. Order matters: backslash first,
        then other specials, and finally turn real newlines into the
        literal '\\n' sequence drawtext understands (do NOT collapse them
        to spaces or multi-line text silently overflows the frame)."""
        if text is None:
            return ""
        s = str(text)
        s = s.replace("\\", "\\\\")
        s = s.replace(":", "\\:")
        s = s.replace("'", "\u2019")
        s = s.replace("%", "\\%")
        s = s.replace("\n", "\\n")
        return s

    def _split_text(self, text, max_chars=38):
        words = str(text).split()
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
        """Find the emphasis word as a whole word (not a substring match,
        so 'art' won't wrongly match 'start' or 'partager')."""
        if not emphasis_word or not text:
            return text, None, ""

        words = str(text).split()
        target = str(emphasis_word).strip().lower()
        pattern = re.compile(rf"^{re.escape(target)}$", re.IGNORECASE)

        idx = next(
            (i for i, w in enumerate(words) if pattern.match(re.sub(r"[^\wàâäéèêëïîôöùûüç-]", "", w, flags=re.IGNORECASE))),
            None,
        )
        if idx is None:
            return text, None, ""

        before = " ".join(words[:idx]).strip()
        keyword = words[idx].strip()
        after = " ".join(words[idx + 1:]).strip()
        return before, keyword, after

    def _keyword_fontsize(self, keyword):
        """Auto-shrink long keywords so they never overflow a 1080px-wide
        vertical frame (finance terms like 'VOLATILITE' or
        'CAPITALISATION' are long)."""
        length = len(keyword or "")
        if length <= 8:
            return KEYWORD_FONTSIZE_MAX
        if length >= 16:
            return KEYWORD_FONTSIZE_MIN
        # linear interpolation between 8 and 16 chars
        ratio = (length - 8) / 8
        return int(KEYWORD_FONTSIZE_MAX - ratio * (KEYWORD_FONTSIZE_MAX - KEYWORD_FONTSIZE_MIN))

    # ------------------------------------------------------------------
    # Background
    # ------------------------------------------------------------------
    def _base_background(self, duration, palette):
        return ffmpeg.input(
            f"color=c={palette['bg1']}:s={self.width}x{self.height}:d={duration}:r={self.fps}",
            f="lavfi",
        ).video

    # ------------------------------------------------------------------
    # Main render
    # ------------------------------------------------------------------
    def generate(self, scene, duration, output_path, disclaimer=None):
        text = scene.get("text", "")
        mood = scene.get("mood", "pedagogical")
        emphasis_word = scene.get("tts_emphasis_word")
        palette = PALETTE_BY_MOOD.get(mood, DEFAULT_PALETTE)

        # Guard against zero/negative duration breaking ffmpeg expressions
        duration = max(float(duration or 0), 0.1)

        before, keyword, after = self._split_around_emphasis(text, emphasis_word)
        video_stream = self._base_background(duration, palette)

        # Soft tinted layer + subtle vignette so the background never reads as flat
        overlay = ffmpeg.input(
            f"color=c={palette['bg2']}@0.16:s={self.width}x{self.height}:d={duration}:r={self.fps}",
            f="lavfi",
        ).video
        video_stream = ffmpeg.overlay(video_stream, overlay, x=0, y=0)
        video_stream = video_stream.filter("vignette", angle="PI/4.5")

        intro = INTRO_DURATION

        if keyword:
            before_lines = self._split_text(before, 44) if before else []
            after_lines = self._split_text(after, 44) if after else []

            y_top = int(self.height * 0.31)
            y_mid = int(self.height * 0.45)
            y_bot = int(self.height * 0.58)

            slide_x = f"(w-text_w)/2 - {SLIDE_OFFSET_PX}*(1-min(t/{intro},1))"
            alpha_in = f"if(lt(t,{intro}),t/{intro},1)"

            if before_lines:
                video_stream = video_stream.filter(
                    "drawtext",
                    fontfile=self.font_regular,
                    text=self._escape_text("\n".join(before_lines)),
                    fontsize=BODY_FONTSIZE,
                    fontcolor="0xE8EDF2",
                    alpha=alpha_in,
                    x=slide_x,
                    y=y_top,
                    line_spacing=LINE_SPACING,
                    box=1,
                    boxcolor="0x000000@0.16",
                    boxborderw=18,
                )

            kw_fontsize = self._keyword_fontsize(keyword)
            video_stream = video_stream.filter(
                "drawtext",
                fontfile=self.font_bold,
                text=self._escape_text(keyword.upper()),
                fontsize=kw_fontsize,
                fontcolor=palette["accent"],
                alpha=f"if(lt(t,{intro + KEYWORD_DELAY}),(t-{KEYWORD_DELAY})/{intro},1)",
                x="(w-text_w)/2 + 6*sin(t*1.7)",
                y=f"{y_mid} + 4*sin(t*1.2)",
                borderw=2,
                bordercolor="0x000000@0.42",
                box=1,
                boxcolor="0x000000@0.18",
                boxborderw=18,
            )

            if after_lines:
                video_stream = video_stream.filter(
                    "drawtext",
                    fontfile=self.font_regular,
                    text=self._escape_text("\n".join(after_lines)),
                    fontsize=BODY_FONTSIZE,
                    fontcolor="0xD9E2EC",
                    alpha=alpha_in,
                    x=slide_x,
                    y=y_bot,
                    line_spacing=LINE_SPACING,
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
                fontsize=SOLO_FONTSIZE,
                fontcolor="0xE8EDF2",
                alpha=f"if(lt(t,{intro}),t/{intro},1)",
                x="(w-text_w)/2 + 5*sin(t*1.5)",
                y=y_center,
                line_spacing=14,
                box=1,
                boxcolor="0x000000@0.18",
                boxborderw=18,
            )

        # Progress bar (track + fill)
        video_stream = video_stream.filter(
            "drawbox",
            x=0,
            y=self.height - PROGRESS_BAR_MARGIN,
            w=self.width,
            h=PROGRESS_BAR_HEIGHT,
            color=f"{palette['accent']}@0.22",
            t="fill",
        )
        video_stream = video_stream.filter(
            "drawbox",
            x=0,
            y=self.height - PROGRESS_BAR_MARGIN,
            w=f"iw*min(t/{duration},1)",
            h=PROGRESS_BAR_HEIGHT,
            color=f"{palette['accent']}@0.95",
            t="fill",
        )

        # Optional legal disclaimer (recommended for finance content on
        # TikTok/YouTube — small, unobtrusive, bottom of frame)
        if disclaimer:
            video_stream = video_stream.filter(
                "drawtext",
                fontfile=self.font_regular,
                text=self._escape_text(disclaimer),
                fontsize=22,
                fontcolor="0xA9B4C0@0.85",
                x="(w-text_w)/2",
                y=self.height - 46,
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
            print(f"\u274c Echec generation kinetic typography v2 : {error_log}")
            return None
