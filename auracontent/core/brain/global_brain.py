# core/global_brain.py
from dataclasses import dataclass, field
from typing import Any
from channels.registry import CHANNEL_REGISTRY
from core.brain.llm_client import LLMClient
from utils.topic_tracker import load_global_history, save_global_history


@dataclass
class GlobalBrain:
    config: Any
    llm_client: LLMClient
    channels: dict[str, Any] = field(default_factory=dict, init=False)

    def __post_init__(self):
        """
        Instancie dynamiquement toutes les chaînes déclarées dans le registre
        en leur passant la configuration et le client LLM partagés.
        """
        self.channels = {
            name: BrainClass(config=self.config, llm=self.llm_client)
            for name, BrainClass in CHANNEL_REGISTRY.items()
        }
        print(f"🌍 GlobalBrain initialisé avec {len(self.channels)} chaîne(s) active(s).")

    # ==========================================
    # MÉTHODES D'ORCHESTRATION
    # ==========================================

    def run_channel(self, channel_name: str) -> bool:
        """Exécute le pipeline de génération pour une seule chaîne."""
        if channel_name not in self.channels:
            raise ValueError(f"Chaîne inconnue: {channel_name}. Vérifiez channels/registry.py.")
        brain = self.channels[channel_name]
        print(f"\n🚀 Démarrage de la chaîne : {channel_name.upper()}")
        # Selection du sujet par le cerveau spécifique
        topic = brain.pick_topic()
        print(f"🎯 Sujet retenu : {topic}")
        # Vérification anti-doublon inter-chaînes
        if self._is_global_duplicate(topic):
            print(f"⚠️ Annulation : Le sujet '{topic}' a déjà été traité par une autre chaîne.")
            return False
        # Génération du script via le BaseBrain
        brain.generate_script(topic)
        # Enregistrement du succès dans l'historique global
        save_global_history(topic, channel_name)
        print(f"✅ Script validé et sauvegardé pour la chaîne {channel_name.upper()}.")
        return True

    def run_all(self) -> dict[str, bool]:
        """Lance séquentiellement toutes les chaînes actives."""
        print("\n🌍 Lancement de la production multi-chaînes")
        results = {}
        for name in self.channels.key():
            try:
                results[name] = self.run_channel(name)
            except Exception as e:
                print(f" Échec critique sur la chaîne {name} : {e}")
                results[name] = False
        return results

    def _is_global_duplicate(self, topic: str) -> bool:
        """Demande au LLM si le sujet croise l'historique global des autres chaînes."""
        global_history = load_global_history()
        if not global_history or not self.channels:
            return False
        # On emprunte le premier cerveau disponible pour utiliser sa méthode LLM
        dummy_brain = next(iter(self.channels.values()))
        is_dup, matched_topic = dummy_brain.is_duplicate_topic_llm(topic, global_history)
        if is_dup:
            print(f"🔍 Collision détectée avec l'ancien sujet : '{matched_topic}'")
        return is_dup
