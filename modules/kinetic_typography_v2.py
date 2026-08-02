"""
Kinetic Typography v2 — version "pro" pour chaine finance.

Ameliorations vs v1 :
- Le mot-cle de la scene (tts_emphasis_word) est affiche en GRAND et en
  couleur accent, le reste du texte en plus petit et en blanc/gris clair
  => hierarchie visuelle, comme dans les explainers finance pro.
- Mouvement directionnel (slide-in + scale) au lieu d'un simple fade,
  pour un effet "le mot atterrit" plutot que "le mot apparait mollement".
- Fond en degrade subtil (pas juste une couleur plate) pour eviter l'effet
  "diapo PowerPoint".
- Une fine ligne de progression en bas d'ecran (comme une barre de lecture)
  pour renforcer le cote "pro/dashboard financier".
- Rendu force en 1080x1920 60fps-ready, crf bas pour un rendu net (pas de
  pixelisation, cf. bonnes pratiques kinetic typography).
"""

import os
import ffmpeg


PALETTE_BY_MOOD = {
    "confident": {"bg1": "0x0B1424", "bg2": "0x152238", "accent": "0x00D9B5"},
    "sharp":     {"bg1": "0x140E1F", "bg2": "0x231433", "accent": "0xFF5C5C"},
    "clear":     {"bg1": "0x0A1B2A", "bg2": "0x123047", "accent": "0x4CC9F0"},
    "pedagogical": {"bg1": "0x0C1420", "bg2": "0x18293D", "accent": "0xFFC857"},
    "engaging":  {"bg1": "0x0D1B2A", "bg2": "0x1B2F4A", "accent": "0x06D6A0"},
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
                print(f"⚠️ Police manquante : {path} (a telecharger gratuitement sur Google Fonts).")

    def _escape_text(self, text):
        text = text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\u2019").replace("%", "\\%")
        return text

    def _split_around_emphasis(self, text, emphasis_word):
        """Separe le texte en 'avant / mot-cle / apres' pour la hierarchie
        visuelle. Si pas de mot-cle, tout le texte reste au format normal."""
        if not emphasis_word:
            return text, None, ""

        words = text.split()
        emphasis_lower = emphasis_word.strip().lower()
        idx = next((i for i, w in enumerate(words) if emphasis_lower in w.lower()), None)

        if idx is None:
            return text, None, ""

        before = " ".join(words[:idx])
        keyword = words[idx]
        after = " ".join(words[idx + 1:])
        return before, keyword, after

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
        settle_time = 0.35

        if keyword:
            y_before = int(self.height * 0.40)
            y_keyword = int(self.height * 0.47)
            y_after = int(self.height * 0.58)

            slide_expr_x = f"if(lt(t,{anim_in}),(w-text_w)/2-40+40*(t/{anim_in}),(w-text_w)/2)"
            scale_alpha = f"if(lt(t,{anim_in}),t/{anim_in},1)"

            if before:
                video_stream = video_stream.filter(
                    "drawtext",
                    fontfile=self.font_regular,
                    text=self._escape_text(before),
                    fontsize=46,
                    fontcolor="0xE8EDF2",
                    alpha=scale_alpha,
                    x=slide_expr_x,
                    y=y_before,
                )

            keyword_alpha = f"if(lt(t,{anim_in + 0.1}),(t-0.1)/{anim_in},1)"
            video_stream = video_stream.filter(
                "drawtext",
                fontfile=self.font_bold,
                text=self._escape_text(keyword.upper()),
                fontsize=78,
                fontcolor=f"{palette['accent']}",
                alpha=keyword_alpha,
                x="(w-text_w)/2",
                y=y_keyword,
                borderw=2,
                bordercolor="0x000000@0.4",
            )

            if after:
                video_stream = video_stream.filter(
                    "drawtext",
                    fontfile=self.font_regular,
                    text=self._escape_text(after),
                    fontsize=46,
                    fontcolor="0xE8EDF2",
                    alpha=scale_alpha,
                    x=slide_expr_x,
                    y=y_after,
                )
        else:
            alpha_expr = f"if(lt(t,{anim_in}),t/{anim_in},1)"
            video_stream = video_stream.filter(
                "drawtext",
                fontfile=self.font_bold,
                text=self._escape_text(text),
                fontsize=58,
                fontcolor="0xE8EDF2",
                alpha=alpha_expr,
                x="(w-text_w)/2",
                y="(h-text_h)/2",
                line_spacing=14,
            )

        bar_width_expr = f"{self.width}*min(t/{duration},1)"
        video_stream = video_stream.filter(
            "drawbox",
            x=0,
            y=self.height - 10,
            w=int(self.width),
            h=6,
            color=f"{palette['accent']}@0.9",
            t="fill",
            enable="1",
        )
        video_stream = video_stream.filter(
            "drawbox",
            x=0,
            y=self.height - 10,
            w=f"{bar_width_expr}",
            h=6,
            color="0xFFFFFF@0.95",
            t="fill",
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
