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

        event_context: descriptif factuel precis (ex: "incendie nocturne de
        novembre 2025, ruines en flammes") issu du script/scene, transmis au
        prompt IA en dernier recours pour generer une image concrete de
        l'evenement plutot qu'une vue generique et intemporelle du lieu.

        NOTE SUR OPENVERSE : ArchiveProvider.get_wikimedia() appelle deja
        Openverse en interne (etape 2 de sa cascade : categorie Wikimedia
        exacte -> Openverse -> plein texte Wikimedia). CORRECTIF : on
        rend ici cet appel explicite et independant, pour pouvoir le
        piloter/logger depuis AssetManager sans devoir lire ArchiveProvider,
        et pour eventuellement changer l'ordre de priorite plus tard sans
        toucher a ArchiveProvider.
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

            # 2. CORRECTIF : tentative Openverse EXPLICITE et independante,
            # au cas ou get_wikimedia() aurait echoue avant meme d'atteindre
            # son etape interne Openverse (ex: si la logique d'ArchiveProvider
            # change plus tard). Filet de securite supplementaire, sans
            # duplication de telechargement grace a is_used()/mark_used()
            # deja geres dans ArchiveProvider.get_openverse().
            print(f"🌍 Nouvelle tentative Openverse directe : '{query}'...")
            if self.archives.get_openverse(query, output_path):
                print("🏛️ Archive Openverse trouvée (tentative directe) !")
                return True, "openverse"

            # 3. Si aucune archive n'a rien, on demande à l'IA de l'imaginer,
            # en enrichissant le prompt avec le contexte factuel de
            # l'evenement si disponible.
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
            # 4. Vidéos d'ambiance Pexels/Pixabay
            print(f"🔍 Recherche vidéo d'ambiance : '{query}'...")
            if self.videos.fetch_background(query, output_path):
                return True, "video"

        # 5. FALLBACK ULTIME POUR TOUT LE MONDE (aussi enrichi si event_context fourni)
        fallback_prompt = f"{query}, {event_context}" if event_context else query
        print(f"🎨 Génération IA de secours : '{fallback_prompt}'...")
        if self.ai.generate_image(fallback_prompt, output_path):
            return True, "ai"

        print(f"❌ Échec total de la récupération d'asset pour : '{query}'")
        return False, "none"
