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

    def _build_structured_prompt(self, query, event_context=None, image_prompt=None):
        """
        Construction d'un prompt structure selon la formule recommandee
        pour la generation d'images photorealistes :
        [Sujet precis] + [Cadrage/angle] + [Lumiere] + [Texture/details] +
        [Palette] + [Ambiance] + [Negatifs].

        CORRECTIF PRINCIPAL : le sujet ('subject') est desormais construit
        en priorite a partir de 'image_prompt' -- la description riche et
        specifique a la scene, generee par le LLM (ex: "photographie en
        noir et blanc d'un couloir de pierre etroit, eclairage a la
        bougie, ambiance lugubre") -- plutot qu'a partir du simple
        'location_name' (ex: "Mont-Dauphin (Cite Vauban)").

        Avant ce correctif, 'image_prompt' n'etait jamais transmis a
        AssetManager : le prompt IA final ne contenait que le nom du lieu,
        produisant des images generiques et repetees (meme seed) qui ne
        correspondaient pas au contenu reel de chaque scene.

        'query' (location_name ou stock_search) est conserve comme
        contexte factuel complementaire (lieu reel), pas comme sujet
        principal, pour ancrer geographiquement l'image sans sacrifier
        la specificite visuelle de la scene.
        """
        if image_prompt and image_prompt.strip():
            subject = image_prompt.strip()
            if query and query.strip() and query.strip().lower() not in subject.lower():
                subject = f"{subject}, lieu réel : {query.strip()}"
        else:
            subject = (query or "").strip()

        if event_context:
            subject = f"{subject}, {event_context.strip()}"

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

    def get_best_asset(self, query, output_path, scene_type="generic", event_context=None, image_prompt=None):
        # ---------------------------------------------------------
        # SCÈNES SPÉCIFIQUES (Lieux réels, personnages, objets)
        # ---------------------------------------------------------
        if scene_type == "specific":
            print(f"🔍 Recherche de la vraie photo historique : '{query}'...")
            if self.archives.get_wikimedia(query, output_path):
                print("🏛️ Vraie archive trouvée !")
                return True, "wiki"

            print(f"🌍 Nouvelle tentative Openverse directe : '{query}'...")
            if self.archives.get_openverse(query, output_path):
                print("🏛️ Archive Openverse trouvée (tentative directe) !")
                return True, "openverse"

            ai_prompt = self._build_structured_prompt(
                query, event_context=event_context, image_prompt=image_prompt
            )

            if event_context:
                print(f"🧠 Archive introuvable. Tentative IA-First contextualisee (prompt structure).")
            else:
                print(f"🧠 Archive introuvable. Tentative IA-First pour : '{query}' (prompt structure).")

            if self.ai.generate_image(ai_prompt, output_path):
                return True, "ai"

            # L'IA a échoué malgré ses propres retries internes (flux/turbo).
            # Au lieu de retenter EXACTEMENT le même prompt, on bascule sur une
            # vidéo d'ambiance générique en dernier recours plutôt que de rien
            # avoir du tout pour la scène.
            print(f"🎬 IA échouée pour '{query}', tentative de secours vidéo générique...")
            generic_fallback_query = "mysterious historical documentary atmosphere"
            if self.videos.fetch_background(generic_fallback_query, output_path):
                return True, "video"

            print(f"❌ Échec total de la récupération d'asset pour : '{query}'")
            return False, "none"

        # ---------------------------------------------------------
        # SCÈNES GÉNÉRIQUES (Ambiance, paysages, émotions)
        # ---------------------------------------------------------
        else:
            print(f"🔍 Recherche vidéo d'ambiance : '{query}'...")
            if self.videos.fetch_background(query, output_path):
                return True, "video"

            # Fallback IA uniquement pour les scènes génériques (pas de doublon
            # possible ici puisque l'IA n'a pas encore été tentée dans cette branche)
            fallback_prompt = self._build_structured_prompt(
                query, event_context=event_context, image_prompt=image_prompt
            )
            print(f"🎨 Génération IA de secours (prompt structure)...")
            if self.ai.generate_image(fallback_prompt, output_path):
                return True, "ai"

            print(f"❌ Échec total de la récupération d'asset pour : '{query}'")
            return False, "none"