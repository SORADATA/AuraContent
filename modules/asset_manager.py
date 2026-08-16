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

    def get_best_asset(self, query, output_path, scene_type="generic", event_context=None):
        """
        Orchestrateur principal.
        scene_type: 'generic' (vagues, ambiance) ou 'specific' (personnage, événement précis).

        CORRECTIF : nouveau parametre optionnel event_context. Permet de
        transmettre un descriptif factuel precis (ex: "incendie nocturne
        de novembre 2025, ruines en flammes") issu du script/scene, afin
        que le prompt IA genere une image concrete de l'evenement plutot
        qu'une vue generique et intemporelle du lieu. Utile notamment
        quand aucune archive (Wikimedia/Openverse) ne peut exister pour
        un evenement recent, car ces sources ne contiennent jamais de
        photos de presse recentes sous copyright.
        """

        # ---------------------------------------------------------
        # SCÈNES SPÉCIFIQUES (Lieux réels, personnages, objets)
        # ---------------------------------------------------------
        if scene_type == "specific":
            # 1. On cherche d'ABORD la vraie photo dans les archives !
            print(f"🔍 Recherche de la vraie photo historique : '{query}'...")
            if self.archives.get_wikimedia(query, output_path):
                print("🏛️ Vraie archive trouvée !")
                return True, "wiki"

            # 2. Si Wikipédia n'a rien, on demande à l'IA de l'imaginer,
            # en enrichissant le prompt avec le contexte factuel de
            # l'evenement si disponible (CORRECTIF).
            ai_prompt = query
            if event_context:
                ai_prompt = f"{query}, {event_context}"
                print(f"🧠 Archive introuvable. Tentative IA-First contextualisee : '{ai_prompt}'.")
            else:
                print(f"🧠 Archive introuvable. Tentative IA-First pour : '{query}'.")

            if self.ai.generate_image(ai_prompt, output_path):
                return True, "ai"

        # ---------------------------------------------------------
        # SCÈNES GÉNÉRIQUES (Ambiance, paysages, émotions)
        # ---------------------------------------------------------
        else:
            # 3. Vidéos d'ambiance Pexels
            print(f"🔍 Recherche vidéo d'ambiance : '{query}'...")
            if self.videos.fetch_background(query, output_path):
                return True, "video"

        # 4. FALLBACK ULTIME POUR TOUT LE MONDE (aussi enrichi si event_context fourni)
        fallback_prompt = f"{query}, {event_context}" if event_context else query
        print(f"🎨 Génération IA de secours : '{fallback_prompt}'...")
        if self.ai.generate_image(fallback_prompt, output_path):
            return True, "ai"

        print(f"❌ Échec total de la récupération d'asset pour : '{query}'")
        return False, "none"
