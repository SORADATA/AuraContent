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
        """
        Orchestrateur principal.
        scene_type: 'generic' (vagues, ambiance) ou 'specific' (personnage, événement précis).

        query: pour les scenes 'specific', il s'agit du location_name (utilise
        pour les recherches d'archives Wikimedia/Openverse, qui ont besoin
        d'un nom propre). Pour les scenes 'generic', il s'agit du
        stock_search (mot-cle anglais court, utilise pour les recherches
        video Pexels/Pixabay).

        event_context: descriptif factuel precis (ex: "incendie nocturne de
        novembre 2025, ruines en flammes") issu du script/scene, transmis au
        prompt IA en dernier recours pour generer une image concrete de
        l'evenement plutot qu'une vue generique et intemporelle du lieu.

        image_prompt: description visuelle riche et specifique a la scene,
        generee par le LLM (ex: "photographie en noir et blanc d'un couloir
        de pierre étroit, éclairage à la bougie, ambiance lugubre").
        CORRECTIF : desormais transmise et utilisee comme coeur du prompt
        IA, pour que l'image generee corresponde reellement au contenu
        narratif de la scene plutot qu'a une vue generique du lieu.
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
            # avec un prompt structure construit a partir de l'image_prompt
            # specifique a la scene (CORRECTIF), enrichi du lieu reel et du
            # contexte factuel eventuel.
            ai_prompt = self._build_structured_prompt(
                query, event_context=event_context, image_prompt=image_prompt
            )

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
            # 4. Vidéos d'ambiance Pexels/Pixabay.
            # 'query' ici doit être stock_search (mot-clé anglais court),
            # transmis correctement depuis main.py (CORRECTIF).
            print(f"🔍 Recherche vidéo d'ambiance : '{query}'...")
            if self.videos.fetch_background(query, output_path):
                return True, "video"

        # 5. FALLBACK ULTIME POUR TOUT LE MONDE (prompt structure aussi,
        # incluant image_prompt si disponible)
        fallback_prompt = self._build_structured_prompt(
            query, event_context=event_context, image_prompt=image_prompt
        )
        print(f"🎨 Génération IA de secours (prompt structure)...")
        if self.ai.generate_image(fallback_prompt, output_path):
            return True, "ai"

        print(f"❌ Échec total de la récupération d'asset pour : '{query}'")
        return False, "none"