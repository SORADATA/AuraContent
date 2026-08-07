import os
import re
import json
import random
from datetime import datetime, timedelta
from openai import OpenAI
from dotenv import load_dotenv

try:
    from modules.utils.zernio_client_finance import get_latest_videos_stats
except ImportError:
    print("⚠️ Module zernio_client introuvable. Création de données factices pour le test.")
    def get_latest_videos_stats(): return None

try:
    from modules.utils.market_data_client import get_market_signals
except ImportError:
    print("⚠️ Module market_data_client introuvable. Aucune donnée de marché live injectée.")
    def get_market_signals(**kwargs): return None

try:
    from filelock import FileLock
    FILELOCK_AVAILABLE = True
except ImportError:
    FILELOCK_AVAILABLE = False

load_dotenv()

GROQ_MODEL = "llama-3.3-70b-versatile"
GEMINI_MODEL = "gemini-flash-latest"

ACCENTED_CHARS = "éèêëàâäùûüçîïôœ"

ACCENT_INSTRUCTION = (
    "IMPERATIF ORTHOGRAPHE : le francais doit etre parfaitement accentue "
    "(accents obligatoires). Exemples : 'epargne' avec accent, 'interet' avec "
    "accent, 'strategie' avec accent, 'benefice' avec accent."
)

COMPLIANCE_INSTRUCTION = (
    "REGLE DE CONFORMITE (AMF) ABSOLUE : Tu adoptes un ton de 'révélation' et de 'secret', "
    "MAIS ce contenu reste de l'éducation financière. Ne donne JAMAIS de conseil en investissement personnalisé. "
    "N'utilise jamais de formulations impératives du type 'achète cette action', 'investis là-dedans'. "
    "Parle des 'mécanismes', des 'règles cachées', de 'ce que font les riches'. "
    "N'invente aucune promesse de gain garanti."
)

COMPLIANCE_RETRY_INSTRUCTION = (
    "ATTENTION - LA GENERATION PRECEDENTE A ECHOUE LE CONTROLE DE CONFORMITE. "
    "Même avec un ton mystérieux et percutant, tu ne dois formuler AUCUN conseil direct d'achat. "
    "Garde le mystère, mais reste éducatif. " + COMPLIANCE_INSTRUCTION
)

PERSONA_INSTRUCTION = (
    "PERSONA : Tu n'es plus un prof de finance ennuyeux. Tu es un 'insider', un initié "
    "qui révèle les rouages cachés de l'argent et du système économique avec un ton direct, "
    "mystérieux, et légèrement provocateur. Ta promesse globale est : 'Je t'explique l'argent en moins d'une minute'. "
    "Le spectateur doit avoir l'impression de découvrir un secret jalousement gardé."
)

VISUAL_CONSISTENCY_INSTRUCTION = (
    "COHERENCE VISUELLE OBLIGATOIRE (STYLE MYSTERE FINANCIER) : "
    "L'esthétique doit être moderne, sombre, luxueuse et cinématique (dark corporate, néons discrets, "
    "ambiance 'Succession' ou 'Loup de Wall Street' version sombre). "
    "Chaque 'image_prompt' doit réutiliser EXACTEMENT la même palette de couleurs sombres et "
    "le même éclairage définis dans 'visual_identity'. Interdiction d'utiliser les mots CGI, 3D, render."
)

# [Garder ici ton dictionnaire CONTENT_PILLARS, ANGLES, et les constantes de fichiers (CURRICULUM_STATE_DIR, etc.) sans modification]
# ... (insère ici tes CONTENT_PILLARS) ...
# Pour l'exemple, je mets une version abrégée des piliers pour la lisibilité
CONTENT_PILLARS = {
    "epargne": {
        "label": "Épargne et pièges bancaires",
        "seed_notions": [
            {"notion": "Pourquoi l'inflation érode ton épargne si elle dort", "niveau": "debutant"},
            {"notion": "Le fonctionnement des intérêts composés (l'effet boule de neige)", "niveau": "debutant"}
        ],
    }
}
ANGLES = ["secret_des_riches", "illusion_du_systeme", "chiffre_choc", "erreur_fatale"]
FORBIDDEN_COMPLIANCE_PHRASES = ["achete cette action", "achete maintenant", "c'est une valeur sure", "rendement garanti", "investis dans"]

# [Garder les fonctions utilitaires: ComplianceViolationError, _flatten_curriculum, _state_lock, _load_curriculum_state, _save_curriculum_state, _get_full_curriculum, _pillar_with_least_coverage, _has_missing_accents, _script_missing_accents, _safe_json_loads, _format_stats_instruction, _format_market_illustration, _clean_single_line_title, _is_valid_topic_candidate, _normalize_title_for_matching, _enrich_stats_with_local_pattern, _score_hook]
# ... (insère ici tes fonctions utilitaires exactes) ...

class ContentBrain:
    # [Garder _build_client, _model_for, _call_with_fallback, expand_curriculum_with_llm, _pick_recycled_notion_with_new_angle, pick_curriculum_notion, record_topic_used, get_newsjacking_topic sans modification majeure (sauf l'ajout de PERSONA_INSTRUCTION si tu le souhaites dans system prompts)]
    # ...

    def get_pedagogical_topic(self, previous_stats_list=None, market_signals=None):
        notion_entry, angle, state = self.pick_curriculum_notion()
        notion = notion_entry["notion"]
        niveau = notion_entry.get("niveau", "intermediaire")

        stats_instruction = _format_stats_instruction(previous_stats_list, label="sujet")
        market_instruction = _format_market_illustration(market_signals, notion)

        messages = [
            {
                "role": "system",
                "content": (
                    f"{PERSONA_INSTRUCTION} "
                    "Transforme la notion financière ennuyeuse fournie en un titre accrocheur, "
                    "qui ressemble à une révélation choquante ou un secret. "
                    "FORMAT EXIGÉ : Commence toujours par 'ARGENT #XX :' (invente un numéro aléatoire entre 01 et 99). "
                    "Exemple : 'ARGENT #04 : Pourquoi ton salaire augmente mais tu t'appauvris.' "
                    "Réponds UNIQUEMENT avec un seul titre en français, sur UNE seule ligne. "
                    f"{ACCENT_INSTRUCTION} {COMPLIANCE_INSTRUCTION}"
                )
            },
            {
                "role": "user",
                "content": (
                    f"Notion à enseigner (niveau {niveau}) : {notion}\n"
                    f"Angle de révélation imposé : {angle.replace('_', ' ')}\n"
                    "Transforme cela en titre mystérieux et percutant."
                    + stats_instruction
                    + market_instruction
                )
            }
        ]
        
        # Logique de fallback classique...
        last_topic = ""
        for attempt in range(2):
            content, _ = self._call_with_fallback(messages, temperature=0.85)
            topic = _clean_single_line_title(content)
            last_topic = topic
            if _is_valid_topic_candidate(topic):
                return {
                    "topic": topic, "notion": notion, "niveau": niveau,
                    "angle": angle, "pillar": notion_entry.get("pillar"), "state": state,
                }
            print(f"⚠️ Sujet invalide généré (tentative {attempt + 1}) : {topic}")

        raise ValueError(f"Impossible d'obtenir un sujet valide : {last_topic}")

    def generate_hook_variants(self, topic, notion=None, angle=None, n=5, previous_stats_list=None):
        print(f"Génération de {n} hooks mystères pour: {topic}...")
        stats_instruction = _format_stats_instruction(previous_stats_list, label="hooks")
        
        prompt = f"""
{PERSONA_INSTRUCTION}

SUJET / TITRE :
{topic}
NOTION CACHÉE : {notion}

OBJECTIF :
Génère {n} hooks différents. Le hook est la toute première phrase de la vidéo (max 3 secondes).
Il doit créer un choc cognitif, révéler une dissonance ou dénoncer une illusion du système financier.

REGLES :
- 12 à 18 mots max. Phrase très orale, percutante.
- Ne mentionne PAS le préfixe 'ARGENT #XX' dans le texte lu à voix haute, c'est juste pour le titre visuel.
- Varie les approches : le piège invisible, le secret des ultra-riches, la fausse croyance populaire.
- Interdiction d'utiliser : "Aujourd'hui", "Bienvenue", "Dans cette vidéo", "Savais-tu que".
- {COMPLIANCE_INSTRUCTION}

FORMAT DE SORTIE (JSON) :
{{
  "analyse_agent": "Pourquoi ces hooks vont retenir l'attention.",
  "hooks": [
    {{
      "text": "Phrase du hook.",
      "pattern": "illusion | secret | choc",
      "raison": "Pourquoi ça marche."
    }}
  ]
}}
"""
        messages = [
            {"role": "system", "content": f"Produis uniquement du JSON valide. {ACCENT_INSTRUCTION}"},
            {"role": "user", "content": prompt},
        ]
        content, _ = self._call_with_fallback(messages, temperature=1.0, json_mode=True)
        data = _safe_json_loads(content)
        return data.get("hooks")

    def generate_script_with_target(self, topic, notion=None, angle=None, scene_count=11, chosen_hook=None):
        if scene_count < 6: raise ValueError("scene_count doit être >= 6.")

        hook_instruction = (
            "La scene 1 doit reprendre exactement ce hook : " + json.dumps(chosen_hook, ensure_ascii=False)
        ) if chosen_hook else "Scene 1 - hook : Accroche percutante et mystérieuse."

        skeleton_dict = {
            "title": topic,
            "notion_enseignee": notion or "",
            "visual_identity": "Consistent modern dark cinematic finance world, sleek corporate aesthetic, deep shadows with subtle neon accents, highly photorealistic",
            "audio_profile": "French premium narrator, confident, slightly mysterious, sharp, insider tone, natural pacing",
            "scenes": [
                {
                    "id": 1,
                    "text": "Phrase française.",
                    "voice_direction": "French premium narrator, intriguing, revealing a secret",
                    "pause_after_ms": 300,
                    "stock_search": "dark modern finance background",
                    "image_prompt": "Detailed English visual prompt following the modular structure, matching visual_identity strictly",
                    "mood": "intriguing",
                    "role": "hook"
                }
            ]
        }
        json_skeleton = json.dumps(skeleton_dict, ensure_ascii=False, indent=2)

        def build_prompt(compliance_block):
            lines = [
                PERSONA_INSTRUCTION,
                "",
                f"TITRE DE LA VIDÉO : {topic}",
                f"VERITABLE NOTION A ENSEIGNER : {notion}",
                "",
                "STRUCTURE NARRATIVE (Le format 'Révélation') :",
                f"- {hook_instruction}",
                "- Scene 2 - L'Illusion : Montre ce que 99% des gens croient à tort sur ce sujet.",
                "- Scene 3 - La Faille : Explique pourquoi cette croyance les maintient dans la 'rat race' ou leur fait perdre de l'argent.",
                f"- Scenes 4 à {scene_count - 3} - Le Mécanisme Caché (La réalité) : Décortique comment le système fonctionne vraiment pas à pas.",
                f"- Scene {scene_count - 2} - L'Exemple Chiffré : Un cas concret et frappant.",
                f"- Scene {scene_count - 1} - La Règle d'Or : Une phrase mémorable à retenir pour changer sa vision.",
                f"- Scene {scene_count} - Outro : Un call-to-action mystérieux ou une question ouverte (ex: 'Et toi, de quel côté es-tu ?').",
                "",
                "REGLES VISUELLES (MYSTERE FINANCIER) :",
                "- 'image_prompt' DOIT suivre l'ambiance définie (sombre, luxueux, financier, cinématique).",
                "- PAS de 3D, PAS de CGI, uniquement du photoréalisme.",
                "",
                compliance_block,
                VISUAL_CONSISTENCY_INSTRUCTION,
                "",
                "FORMAT EXIGÉ : Uniquement du JSON valide calqué sur ce squelette :"
            ]
            lines.append(json_skeleton)
            return "\n".join(lines)

        # Logique de retry pour JSON et conformité (identique à ton script existant)
        for attempt in range(2):
            compliance_block = COMPLIANCE_INSTRUCTION if attempt == 0 else COMPLIANCE_RETRY_INSTRUCTION
            prompt = build_prompt(compliance_block)
            messages = [
                {"role": "system", "content": f"Uniquement du JSON valide pour {scene_count} scènes. {ACCENT_INSTRUCTION}"},
                {"role": "user", "content": prompt}
            ]
            
            content, provider_used = self._call_with_fallback(messages, temperature=0.7, json_mode=True)
            data = _safe_json_loads(content)
            
            try:
                # Appelle ici ta fonction _validate_script originale
                self._validate_script(data, scene_count)
                return data
            except ComplianceViolationError as e:
                print(f"🚫 Violation de conformité détectée : {e}")
                continue
                
        raise RuntimeError("Échec de génération après 2 tentatives.")
