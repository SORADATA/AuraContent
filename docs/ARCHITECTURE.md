# Architecture AuraContent (multi-chaînes)

Principe : **un moteur générique + un dossier par chaîne** qui ne contient que ce qui la différencie (prompts, voix, ton, style visuel). Plus de fichiers suffixés `_finance`.

## Arborescence cible

```text
AuraContent/
├── .github/
├── config/
│   ├── __init__.py
│   └── settings.py              # ex constants.py (modèles LLM, chemins, clés via .env)
├── core/                        # le moteur générique
│   ├── __init__.py
│   ├── base_brain.py            # BaseBrain : logique commune (LLM, fallback, JSON, retry)
│   ├── global_brain.py          # GlobalBrain : planifie et orchestre toutes les chaînes
│   ├── llm_client.py            # Groq / OpenRouter + fallback (ex imports de brain.py)
│   ├── pipeline.py              # script → audio → visuels → composition
│   └── models.py                # dataclasses : Topic, Script, Scene, Video
├── services/                    # briques réutilisables, sans logique de chaîne
│   ├── __init__.py
│   ├── audio/                   # audio.py, audio_engine.py, tts
│   ├── visuals/                 # ai_image.py, character_engine.py, scene_animator.py
│   ├── video/                   # composer.py
│   ├── scraping/                # video_scraper/
│   └── assets/                  # asset_manager.py
├── channels/                    # une chaîne = un dossier
│   ├── __init__.py
│   ├── base_channel.py          # classe abstraite BaseChannel
│   ├── registry.py              # {"finance": FinanceChannel, ...}
│   ├── finance/
│   │   ├── __init__.py
│   │   ├── config.py            # voix, langue, durée, couleurs, catégories
│   │   ├── brain.py             # FinanceBrain(BaseBrain)
│   │   ├── prompts/             # system.md, script.md, titles.md
│   │   └── assets/              # musiques, polices, intro
│   ├── mystery/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── brain.py
│   │   ├── prompts/
│   │   └── assets/
│   └── kids/
│       ├── __init__.py
│       ├── config.py
│       ├── brain.py
│       ├── scriptwriter.py      # ex kids_scriptwriter.py
│       └── tts.py               # ex kids_tts.py
├── utils/
│   ├── __init__.py
│   └── topic_tracker.py         # historique, anti-doublons (par chaîne + global)
├── data/                        # ignoré par git
│   ├── finance/history.json
│   ├── mystery/history.json
│   └── global/
├── output/                      # vidéos générées (ignoré par git)
├── tests/
├── scripts/                     # utilitaires ponctuels
├── docs/
├── main.py                      # point d'entrée UNIQUE
├── app.py                       # interface (si Streamlit)
├── requirements.txt             # remplace packages.txt
├── README.md
├── CHANGELOG.md
├── CONTRIBUTING.md
├── LICENSE
├── .releaserc
├── .env.example
└── .gitignore
```

## Où mettre les constantes

| Type de constante | Où | Exemple |
|---|---|---|
| Commune à toutes les chaînes | `config/settings.py` | modèles LLM, chemins, timeouts |
| Propre à une chaîne | `channels/<chaîne>/config.py` | voix TTS, langue, durée, couleurs |
| Secret | `.env` (jamais dans le code) | clés API |

Question à se poser : *« la chaîne mystère aurait-elle une valeur différente ? »* Si oui, c'est dans le dossier de la chaîne.

## Le principe des Brains

```python
# core/base_brain.py
class BaseBrain:
    channel_name = "base"

    def __init__(self, config, llm_client):
        self.config = config
        self.llm = llm_client

    def pick_topic(self): ...           # commun : anti-doublons via topic_tracker
    def write_script(self, topic): ...  # commun : appelle le LLM avec les prompts de la chaîne
    def load_prompt(self, name): ...    # lit channels/<nom>/prompts/<name>.md


# channels/finance/brain.py
class FinanceBrain(BaseBrain):
    channel_name = "finance"

    def write_script(self, topic):      # surcharge seulement si nécessaire
        data = get_latest_videos_stats()
        return super().write_script(topic, extra_context=data)


# core/global_brain.py
class GlobalBrain:
    def __init__(self, channels: dict[str, BaseBrain]): ...
    def plan_week(self): ...                    # répartit les vidéos entre chaînes
    def is_duplicate_global(self, topic): ...   # évite les sujets similaires entre chaînes
    def run(self, channel: str): ...            # délègue au brain de la chaîne
```

Le `GlobalBrain` ne fait pas le travail des chaînes : il planifie, évite les doublons inter-chaînes, gère les quotas d'API et centralise les stats.

## Point d'entrée

```bash
python main.py --channel finance
python main.py --channel mystery --dry-run
python main.py --all                 # via le GlobalBrain
```

## Correspondance avec l'existant

| Actuel | Destination |
|---|---|
| `constants.py` | `config/settings.py` (+ `channels/*/config.py` pour le spécifique) |
| `modules/brain.py` | `core/base_brain.py` + `core/llm_client.py` |
| `modules/brain_finance.py` | `channels/finance/brain.py` |
| `modules/composer.py` + `composer_finance.py` | `services/video/composer.py` |
| `modules/audio.py` + `audio_engine_finance.py` | `services/audio/` |
| `modules/asset_manager*.py` | `services/assets/asset_manager.py` |
| `modules/ai_image.py`, `character_engine.py`, `scene_animator.py` | `services/visuals/` |
| `modules/video_scraper/` | `services/scraping/` |
| `modules/kids_scriptwriter.py`, `kids_tts.py` | `channels/kids/` |
| `modules/utils/` | `utils/` |
| `main.py` + `main_finance.py` | un seul `main.py` avec `--channel` |

## Plan de migration

Un commit par étape, avec `git mv` pour conserver l'historique.

1. **Squelette** : créer les dossiers et les `__init__.py`, sans rien déplacer.
2. **Services génériques** : déplacer `audio`, `visuals`, `video`, `assets`, corriger les imports.
3. **BaseBrain** : extraire de `brain.py`, puis `brain_finance.py` devient `FinanceBrain`. Vérifier que la finance marche à l'identique.
4. **Fusion des doublons** : `composer` / `composer_finance`, etc., en déplaçant les différences dans `channels/finance/config.py`.
5. **Chaîne mystère** : le vrai test. Un dossier et un `config.py` à créer suffisent si l'architecture tient.

## Règles à respecter (sans package)

- Toujours lancer depuis la racine : `python main.py`.
- Un `__init__.py` dans chaque dossier.
- Imports absolus depuis la racine : `from core.base_brain import BaseBrain`.
- Ne pas nommer un dossier comme un module standard (`json/`, `random/`, `time/`...).

## Hygiène

- Ajouter `data/`, `output/`, `.venv/` au `.gitignore`.
- Créer un environnement : `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`, puis le sélectionner dans VS Code (barre du bas, « Select Python Interpreter »).
- Ne jamais versionner les secrets ni l'historique des sujets.
- Ajouter quelques tests minimaux sur `topic_tracker` et `BaseBrain`.

