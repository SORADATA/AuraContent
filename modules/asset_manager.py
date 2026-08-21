import os
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
        Construction d'un prompt structuré pour garantir le photoréalisme
        et s'éloigner du côté "3D/CGI" des IA standards.
        """
        if image_prompt and image_prompt.strip():
            subject = image_prompt.strip()
            if query and query.strip() and query.strip().lower() not in subject.lower():
                subject = f"{subject}, lieu réel : {query.strip()}"
        else:
            subject = (query or "").strip()

        if event_context:
            subject = f"{subject}, {event_context.strip()}"

        composition = "documentary photography, eye-level perspective"
        lighting = "dramatic natural lighting, moody shadows, authentic exposure"
        texture = "visible material details, realistic weathered surfaces, natural imperfections, subtle film grain"
        palette = "muted desaturated tones, dark cinematic color grading"
        mood = "tense, mysterious, documentary atmosphere, photojournalistic feel"
        
        # Nouveaux négatifs stricts pour la V3
        negatives = "symmetrical AI composition, overly perfect architecture, plastic skin, fantasy lighting, text, watermark, logo, 3D render, CGI, illustration, cartoon"

        structured_prompt = (
            f"{subject}. {composition}. {lighting}. {texture}. "
            f"{palette}. {mood}. photorealistic, ultra-realistic, "
            f"35mm real-world photography. {negatives}."
        )

        return structured_prompt

    def get_best_asset(self, query, output_path, scene_type="generic", event_context=None, image_prompt=None):
        """
        Orchestrateur qui cherche LA meilleure source primaire (Wikimedia, Pexels, ou IA).
        """
        if scene_type == "specific":
            print(f"🔍 Recherche de la vraie photo historique : '{query}'...")
            if self.archives.get_wikimedia(query, output_path):
                print("🏛️ Vraie archive trouvée !")
                return True, "wiki"

            print(f"🌍 Nouvelle tentative Openverse directe : '{query}'...")
            if self.archives.get_openverse(query, output_path):
                print("🏛️ Archive Openverse trouvée !")
                return True, "openverse"

            ai_prompt = self._build_structured_prompt(query, event_context=event_context, image_prompt=image_prompt)
            if event_context:
                print(f"🧠 Archive introuvable. Tentative IA-First contextualisée.")
            else:
                print(f"🧠 Archive introuvable. Tentative IA-First pour : '{query}'.")

            if self.ai.generate_image(ai_prompt, output_path):
                return True, "ai"

        else:
            print(f"🔍 Recherche vidéo d'ambiance stock : '{query}'...")
            if self.videos.fetch_background(query, output_path):
                return True, "video"

        # FALLBACK ULTIME
        fallback_prompt = self._build_structured_prompt(query, event_context=event_context, image_prompt=image_prompt)
        print(f"🎨 Génération IA de secours...")
        if self.ai.generate_image(fallback_prompt, output_path):
            return True, "ai"

        print(f"❌ Échec total de la récupération d'asset pour : '{query}'")
        return False, "none"

    def get_scene_variants(self, scene, output_dir):
        """
        MOTEUR DE MICRO-PLANS V3
        Génère les variantes multiples d'une scène dictées par le RetentionPlanner.
        Mélange astucieusement de vraies archives (Plan A) et des focus IA (Plans B, C).
        """
        scene_id = scene["id"]
        scene_type = scene.get("scene_type", "generic")
        query = scene.get("location_name") if scene_type == "specific" else scene.get("stock_search")
        event_context = scene.get("event_context")
        
        image_prompt = scene.get("image_prompt") or scene.get("text", "")
        visual_identity = scene.get("visual_identity")

        # Le Planner dicte le nombre de plans nécessaires pour dynamiser la scène
        num_variants = scene.get("visual_variants", 2)
        variant_names = ["a", "b", "c", "d"][:num_variants]
        
        variants = []

        for idx, variant in enumerate(variant_names):
            ext = ".mp4" if (idx == 0 and scene_type == "generic") else ".png"
            temp_path = os.path.join(output_dir, f"scene_{scene_id}_{variant}_temp{ext}")
            
            success = False
            source_type = "ai"

            # PLAN A : On cherche la preuve principale (Vraie archive ou Vidéo d'ambiance)
            if idx == 0:
                success, source_type = self.get_best_asset(
                    query=query, 
                    output_path=temp_path, 
                    scene_type=scene_type, 
                    event_context=event_context, 
                    image_prompt=image_prompt
                )
            
            # PLANS B & C : On force l'IA pour créer des gros plans ou détails liés au Plan A
            else:
                ai_prompt = self._build_structured_prompt(query, event_context, image_prompt)
                success = self.ai.generate_image(
                    prompt_text=ai_prompt,
                    output_path=temp_path,
                    visual_identity=visual_identity,
                    variant=variant,  # Cela va déclencher les cadrages close-up / evidence !
                    scene_id=scene_id,
                    retries=1
                )
                source_type = "ai"

            if success and os.path.exists(temp_path):
                # On renomme le fichier en injectant la source pour que Composer affiche le bon crédit !
                # Ex: scene_wiki_1_a.png ou scene_ai_1_b.png
                final_path = os.path.join(output_dir, f"scene_{source_type}_{scene_id}_{variant}{ext}")
                os.rename(temp_path, final_path)
                variants.append(final_path)

        return variants