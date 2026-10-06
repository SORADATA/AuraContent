import json
from dataclasses import dataclass
from typing import Any, dict, list
from core.brain.llm_client import LLMClient


@dataclass
class BaseBrain:
    config: Any
    llm: LLMClient
    channel_name: str = "base"

    # ==========================================
    # MÉTHODES GÉNÉRIQUES (Communes à tous)
    # ==========================================

    def is_duplicate_topic_llm(self, candidate, history):
        """Vérifie si le concept du sujet existe déjà dans l'historique."""
        if not history:
            return False, None
        recent = history[-15:]
        prompt = f"""Voici un nouveau sujet de video : "{candidate}"

Voici les 15 derniers sujets deja publies :
{chr(10).join(f"- {t}" for t in recent)}

Le nouveau sujet reprend-il le meme TYPE de concept qu'un des sujets deja publies ?
Reponds uniquement en JSON : {{"is_duplicate_type": true/false, "matched_topic": "..." ou null}}"""

        # Appel au client LLM
        data = self.llm.call_json_with_retry(
            [{"role": "user", "content": prompt}],
            temperature=0.1,
            max_completion_tokens=300
        )
        if data.get("is_duplicate_type"):
            return True, data.get("matched_topic")
        return False, None

    def generate_hook_variants(self, topic, n=5, previous_stats_list=None):
        """Génère N variantes d'accroches de façon générique."""
        # On peut imaginer une méthode self.get_hook_system_prompt() surchargeable
        prompt = f"""SUJET:\n{topic}\n\nGENERE {n} hooks viraux en francais.\n
        RETURNS JSON:
        {{
          "hooks": [
            {{"text": "...", "pattern": "question", "raison": "..."}}
          ]
        }}"""

        messages = [
            {"role": "system", "content": "Tu produis uniquement du JSON valide sans texte autour."},
            {"role": "user", "content": prompt},
        ]

        data = self.llm.call_json_with_retry(messages, temperature=1.1, max_completion_tokens=2000)
        hooks = data.get("hooks", [])
        if not isinstance(hooks, list) or len(hooks) == 0:
            return [{"text": topic, "pattern": "default", "raison": ""}]
        return hooks[:n]

    def generate_script(self, topic, chosen_hook=None):
        """Point d'entrée standard pour générer un script."""
        # On lit le nombre de scènes cible depuis la config de la chaîne
        target_scenes = getattr(self.config, 'DEFAULT_SCENE_COUNT', 11)
        return self.generate_script_with_target(
            topic, scene_count=target_scenes, chosen_hook=chosen_hook
            )

    def generate_script_with_target(self, topic, scene_count=11, chosen_hook=None, max_retries=2):
        """
        Gère la boucle de repli sur le nombre de scènes : si le LLM échoue (timeout/tokens),
        on retente avec moins de scènes (ex: 11 -> 8 -> 5).
        """
        candidate_counts = []
        sc = scene_count
        while sc >= 6 and len(candidate_counts) < 3:
            candidate_counts.append(sc)
            sc -= 3
        if not candidate_counts:
            candidate_counts = [scene_count]

        last_error = None
        for idx, candidate_count in enumerate(candidate_counts):
            if idx > 0:
                print(
                    f"⚠️️ Nouvelle tentative avec {candidate_count} scenes pour respecter le budget."
                    )
            try:
                return self._generate_script_attempt(
                    topic, candidate_count, chosen_hook, max_retries
                    )
            except (RuntimeError, ValueError) as e:
                last_error = e
                print(f"❌ Echec de generation avec {candidate_count} scenes : {e}")
                continue

        raise RuntimeError(f"Impossible de generer un script. Derniere erreur : {last_error}")

    def _generate_script_attempt(self, topic, scene_count, chosen_hook, max_retries):
        """
        Gère la boucle de correction (fact-check & validation de structure).
        """
        correction_feedback = ""
        for attempt in range(max_retries + 1):
            # On demande à la classe enfant de construire le prompt spécifique
            messages = self.build_script_prompt(
                topic, scene_count, chosen_hook, correction_feedback
                )
            # Appel au LLM
            data = self.llm.call_json_with_retry(
                messages,
                temperature=0.7,
                max_completion_tokens=min(scene_count * 350 + 1200, 6500)
            )

            scenes = data.get("scenes", [])
            # Validation de base (nombre de scènes)
            if len(scenes) != scene_count:
                if attempt < max_retries:
                    correction_feedback = f"\nCORRECTION OBLIGATOIRE: Genere EXACTEMENT {scene_count} scenes. Tu en as fait {len(scenes)}."
                    continue
                else:
                    raise ValueError(f"Echec du comptage des scènes après {max_retries} tentatives.")

            # Validation structurelle commune
            try:
                self._validate_script_base(data, scene_count)
                # Validation spécifique à la chaîne (optionnelle)
                self.validate_script_specifics(data, topic)
            except ValueError as e:
                if attempt < max_retries:
                    correction_feedback = f"\nCORRECTION OBLIGATOIRE: {e}"
                    continue
                else:
                    raise

            # 5. Vérifications "Métier" (Fact-checking, géo, etc.) déléguées à la sous-classe
            issues = self.check_script_logic(topic, data)
            if issues:
                if attempt < max_retries:
                    correction_feedback = "\nCORRECTION: " + "\n- ".join(issues)
                    continue
                else:
                    print("⚠️ Script généré avec des avertissements ignorés (limite d'essais atteinte).")
            return data

    def _validate_script_base(self, data, expected_scene_count):
        """Applique les valeurs par défaut et vérifie les clés critiques."""
        for idx, scene in enumerate(data.get("scenes", []), start=1):
            if not scene.get("text"):
                raise ValueError(f"Scene {idx} : champ 'text' manquant.")
            # Valeurs par défaut génériques
            scene.setdefault("id", idx)
            scene.setdefault("pause_after_ms", 800)
            scene.setdefault("voice_type", "narrator")
            scene.setdefault("scene_type", "generic")
        if not str(data.get("title", "")).strip():
            data["title"] = "Titre généré"

    # ==========================================
    # MÉTHODES ABSTRAITES (À surcharger)
    # ==========================================

    def pick_topic(self):
        """À implémenter dans les sous-classes (Viral, Stats, etc.)"""
        raise NotImplementedError

    def build_script_prompt(self, topic, scene_count, chosen_hook, correction_feedback):
        """
        Doit retourner la liste d'objets 'messages' pour l'API.
        À implémenter dans MysteryBrain, FinanceBrain...
        """
        raise NotImplementedError

    def validate_script_specifics(self, data, topic):
        """Pour ajouter des règles de validation propres à la chaîne (ex: interdire certains mots)."""
        pass

    def check_script_logic(self, topic, data):
        """
        Retourne une liste de strings contenant les erreurs factuelles/logiques. 
        Si vide, le script est validé.
        """
        return []
