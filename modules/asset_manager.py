from modules.utils.download.utils_assets import load_history
from modules.utils.download.video_provider import VideoProvider
from modules.utils.download.archive_provider import ArchiveProvider
from modules.ai_image import AIImageGenerator


class AssetManager:
    def __init__(self):
        self.history = load_history()
        self.videos = VideoProvider(self.history)
        self.archives = ArchiveProvider(self.history)
        self.ai = AIImageGenerator()

    def _build_structured_prompt(self, query, event_context=None):
        """
        CORRECTIF : construction d'un prompt structure selon la formule
        recommandee pour la generation d'images photorealistes :
        [Sujet precis] + [Cadrage/angle] + [Lumiere] + [Texture/details] +
        [Palette] + [Ambiance] + [Negatifs].

        Avant, le prompt etait une simple concatenation brute
        "query, event_context", sans hierarchie -- les premiers mots d'un
        prompt pesant plus fort sur le resultat final, l'absence de
        structure produisait des images vagues/abstraites plutot que des
        scenes concretes et photorealistes.
        """
        subject = query.strip()

        if event_context:
            # Le contexte factuel (ex: "nocturnal fire, monastery ruins in
            # flames, november 2025") devient le coeur du sujet, pas un
            # simple ajout en fin de phrase.
            subject = f"{query.strip()}, {event_context.strip()}"

        composition = "wide-angle documentary shot, eye-level perspective"
        lighting = "dramatic natural lighting, moody shadows, golden-hour or night ambient light depending on scene"
        texture = "visible material details, realistic weathered surfaces, natural imperfections"
        palette = "muted desaturated tones, dark cinematic color grading"
        mood = "tense, mysterious, documentary atmosphere, photojournalistic feel"
        negatives = "no text, no watermark, no logo, no 3d render, no CGI, no illustration, no cartoon"

        structured_prompt = (
            f"{subject}. {composition}. {lighting}. {texture}. "
            f"{palette}. {mood}. photorealistic, ultra-realistic, "
            f"real-world photography, 8k detail. {negatives}."
        )

        return structured_prompt

    def get_best_asset(self, query, output_path, scene_type="generic", event_context=None):
        """
        Orchestrateur principal.
        scene_type: 'generic' (vagues, ambiance) ou 'specific' (personnage, événement précis).

        event_context: descriptif factuel precis (ex: "incendie nocturne de
        novembre 2025, ruines en flammes") issu du script/scene, transmis au
        prompt IA en dernier recours pour generer une image concrete de
        l'evenement plutot qu'une vue generique et intemporelle du lieu.
        """

        # ---------------------------------------------------------
        # SCÈNES SPÉCIFIQUES (Lieux réels, personnages, objets)
        # ---------------------------------------------------------
        if scene_type == "specific":
            # 1. Wikimedia (catégorie exacte + Openverse intercalaire + plein texte)
            print(f"🔍 Recherche de la vraie photo historique : '{query}'...")
            if self.archives.get_wikimedia(query, output_path):
                print("🏛️ Vraie archive trouvée !")
                return True, "wiki"

            # 2. Tentative Openverse explicite et independante
            print(f"🌍 Nouvelle tentative Openverse directe : '{query}'...")
            if self.archives.get_openverse(query, output_path):
                print("🏛️ Archive Openverse trouvée (tentative directe) !")
                return True, "openverse"

            # 3. Si aucune archive n'a rien, on demande à l'IA de l'imaginer,
            # avec un prompt structure (CORRECTIF) plutot qu'une simple
            # concatenation brute.
            ai_prompt = self._build_structured_prompt(query, event_context=event_context)

            if event_context:
                print(f"🧠 Archive introuvable. Tentative IA-First contextualisee (prompt structure).")
            else:
                print(f"🧠 Archive introuvable. Tentative IA-First pour : '{query}' (prompt structure).")

            if self.ai.generate_image(ai_prompt, output_path):
                return True, "ai"

        # ---------------------------------------------------------
        # SCÈNES GÉNÉRIQUES (Ambiance, paysages, émotions)
        # ---------------------------------------------------------
        else:
            # 4. Vidéos d'ambiance Pexels/Pixabay
            print(f"🔍 Recherche vidéo d'ambiance : '{query}'...")
            if self.videos.fetch_background(query, output_path):
                return True, "video"

        # 5. FALLBACK ULTIME POUR TOUT LE MONDE (prompt structure aussi)
        fallback_prompt = self._build_structured_prompt(query, event_context=event_context)
        print(f"🎨 Génération IA de secours (prompt structure)...")
        if self.ai.generate_image(fallback_prompt, output_path):
            return True, "ai"

        print(f"❌ Échec total de la récupération d'asset pour : '{query}'")
        return False, "none"
