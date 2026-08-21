import re
from typing import Dict, List


class RetentionPlanner:
    """
    Transforme un script documentaire classique en script orienté rétention.

    Principes :
    - hook immédiatement compréhensible
    - progression de tension
    - changement visuel fréquent
    - révélation intermédiaire
    - payoff final
    - possibilité de boucle
    """

    DEFAULT_BEATS = [
        "hook",
        "proof",
        "context",
        "escalation",
        "reveal",
        "payoff",
        "loop",
    ]

    def __init__(self, target_duration=45):
        self.target_duration = max(int(target_duration), 20)

    def _split_sentences(self, text):
        if not text:
            return []

        parts = re.split(r"(?<=[.!?])\s+", text.strip())
        return [p.strip() for p in parts if p.strip()]

    def _estimate_scene_intensity(self, index, total):
        if total <= 1:
            return 1.0

        position = index / max(total - 1, 1)

        # Hook fort
        if position <= 0.10:
            return 1.0

        # Montée
        if position <= 0.40:
            return 0.72 + position

        # Zone de révélation
        if position <= 0.75:
            return 0.90

        # Payoff
        return 1.0

    def _select_visual_role(self, index, total, scene):
        if index == 0:
            return "hook"

        position = index / max(total - 1, 1)

        if scene.get("event_context"):
            if position > 0.60:
                return "reveal"
            return "evidence"

        if position < 0.30:
            return "establishing"

        if position < 0.65:
            return "detail"

        if position < 0.85:
            return "evidence"

        return "payoff"

    def _select_transition(self, index, total):
        if index == 0:
            return "cut"

        position = index / max(total - 1, 1)

        if 0.60 <= position <= 0.85:
            return "cut"

        if position > 0.85:
            return "fade"

        return "cut"

    def _find_emphasis_words(self, text):
        """
        Sélectionne quelques mots forts pour les sous-titres.
        Ce n'est pas du NLP complexe volontairement : il faut rester robuste.
        """
        if not text:
            return []

        candidates = re.findall(
            r"\b[\wÀ-ÿ'-]{5,}\b",
            text
        )

        stopwords = {
            "cette",
            "cette",
            "comme",
            "depuis",
            "avait",
            "avaient",
            "pourtant",
            "alors",
            "entre",
            "après",
            "avant",
            "dans",
            "avec",
            "sans",
            "leurs",
            "notre",
            "votre",
            "cette",
            "elles",
            "nous",
            "vous",
            "sont",
            "était",
            "être",
        }

        scored = []

        for word in candidates:
            normalized = word.lower()

            if normalized in stopwords:
                continue

            score = len(word)

            if normalized in {
                "mort",
                "morte",
                "disparu",
                "disparue",
                "secret",
                "mystère",
                "mystere",
                "preuve",
                "incendie",
                "cadavre",
                "inconnu",
                "jamais",
                "personne",
                "étrange",
                "etrange",
            }:
                score += 10

            scored.append((score, word))

        scored.sort(reverse=True)

        return [word for _, word in scored[:3]]

    def annotate_scene(self, scene, index, total):
        text = scene.get("text", "")

        scene["visual_role"] = self._select_visual_role(
            index,
            total,
            scene
        )

        scene["visual_intensity"] = round(
            self._estimate_scene_intensity(index, total),
            2
        )

        scene["transition"] = self._select_transition(
            index,
            total
        )

        scene["caption_emphasis"] = self._find_emphasis_words(text)

        # Plus une scène est importante, plus elle doit recevoir de variation.
        if scene["visual_role"] in {"hook", "reveal", "payoff"}:
            scene["visual_variants"] = 3
        elif scene["visual_role"] in {"evidence", "detail"}:
            scene["visual_variants"] = 2
        else:
            scene["visual_variants"] = 2

        # SFX potentiel.
        if scene["visual_role"] == "hook":
            scene["sound_effect"] = "impact"
        elif scene["visual_role"] == "reveal":
            scene["sound_effect"] = "reveal"
        elif scene["visual_role"] == "payoff":
            scene["sound_effect"] = "low_hit"
        else:
            scene["sound_effect"] = None

        return scene

    def plan(self, script: List[Dict]):
        if not script:
            return script

        total = len(script)

        for index, scene in enumerate(script):
            self.annotate_scene(
                scene,
                index,
                total
            )

        # Métadonnées globales.
        script[0]["is_hook"] = True

        for scene in script[1:]:
            scene["is_hook"] = False

        script[-1]["is_payoff"] = True

        # Détermine une identité visuelle commune.
        visual_identity = (
            "premium French mystery documentary, "
            "photorealistic real-world cinematography, "
            "desaturated cinematic palette, "
            "natural skin and material textures, "
            "subtle 35mm film grain, "
            "realistic shadows, "
            "restrained dramatic lighting, "
            "European documentary aesthetic"
        )

        for scene in script:
            scene["visual_identity"] = visual_identity

        return script

    def build_hook_instruction(self):
        return (
            "The first scene must function as an immediate hook. "
            "Start with a concrete disturbing fact, contradiction, "
            "unanswered question or unexpected event. "
            "Do not begin with generic historical background. "
            "The viewer must understand within two seconds why "
            "they should keep watching."
        )

    def build_retention_instruction(self):
        return (
            "Structure the short documentary around escalating revelations. "
            "Every scene must introduce either a new fact, a visual proof, "
            "a contradiction, a new question or a reveal. "
            "Avoid filler. Avoid repeating information. "
            "The final scene must provide a satisfying payoff or an unresolved "
            "question strong enough to encourage comments and rewatching."
        )