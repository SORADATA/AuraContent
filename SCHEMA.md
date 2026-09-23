AuraContent/
├── .github/
├── config/
│   ├── settings.py              # ex constants.py (modèles LLM, chemins, clés)
│   └── channels/
│       ├── finance.yaml         # voix, langue, durée, style, fréquence...
│       ├── mystery.yaml
│       └── kids.yaml
├── src/auracontent/
│   ├── core/                    # le moteur générique
│   │   ├── brain/
│   │   │   ├── base_brain.py    # BaseBrain : logique commune (LLM, fallback, JSON, retry)
│   │   │   ├── global_brain.py  # GlobalBrain : orchestre toutes les chaînes
│   │   │   └── llm_client.py    # Groq / OpenRouter + fallback (ex imports de brain.py)
│   │   ├── pipeline.py          # script → audio → visuels → composition
│   │   └── models.py            # dataclasses : Topic, Script, Scene, Video
│   ├── services/                # briques réutilisables, sans logique de chaîne
│   │   ├── audio/               # audio.py, audio_engine, tts
│   │   ├── visuals/             # ai_image.py, scene_animator.py
│   │   ├── video/               # composer.py
│   │   ├── scraping/            # video_scraper/
│   │   └── assets/              # asset_manager.py
│   ├── channels/                # une chaîne = un dossier
│   │   ├── base_channel.py      # classe abstraite BaseChannel
│   │   ├── registry.py          # {"finance": FinanceChannel, ...}
│   │   ├── finance/
│   │   │   ├── brain.py         # FinanceBrain(BaseBrain)
│   │   │   ├── prompts/         # system.md, script.md, titles.md
│   │   │   └── assets/          # musiques, polices, intro
│   │   ├── mystery/
│   │   └── kids/
│   │       ├── brain.py
│   │       ├── scriptwriter.py  # ex kids_scriptwriter.py
│   │       └── tts.py           # ex kids_tts.py
│   └── utils/
│       └── topic_tracker.py     # historique, anti-doublons (par chaîne + global)
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
├── pyproject.toml               # ou requirements.txt (remplace packages.txt)
├── README.md
├── CHANGELOG.md, CONTRIBUTING.md, LICENSE, .releaserc
└── .env.example, .gitignore