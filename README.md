# 🎬 AutoShorts AI — Générateur & Publisher Automatisé de Vidéos "Faceless"

![Views](https://komarev.com/ghpvc/?username=SaarD00-AI-Youtube-Shorts-Generator&style=for-the-badge&color=blue)

**AutoShorts AI** est un pipeline Python entièrement automatisé qui génère des vidéos "faceless" façon YouTube Shorts / TikTok à partir d'un simple sujet, et **les publie automatiquement sur TikTok**.

Le tout tourne dans le cloud via **GitHub Actions** : génération du sujet/script par IA, voix off, sourcing de vidéos stock, montage FFmpeg, stockage cloud via Hugging Face, et publication automatique via API.

---

## ✨ Fonctionnalités clés

| Fonctionnalité | Description |
|---|---|
| ☁️ **100% automatisé cloud** | Exécutions planifiées via **GitHub Actions**. Aucun serveur ni PC local requis. |
| 📱 **Publication auto sur TikTok** | Récupère la dernière vidéo générée et la publie via l'**API Zernio** (mentions IA + anti-doublons). |
| 🤗 **Stockage cloud** | Utilise les datasets **Hugging Face** comme base de données vidéo. |
| 🧠 **Scriptwriting intelligent** | **Google Gemini / Groq** rédige des scripts "edutainment" structurés (Hook → Contexte → Mécanisme → Twist). |
| 🗣️ **Voix off** | Narration générée via `edge-tts`. |
| 🎞️ **Système Dual-Visual** | Télécharge **deux vidéos stock distinctes** par scène depuis **Pexels** pour un effet "split A/B". |
| ✂️ **Montage FFmpeg avancé** | Trim intelligent, split A/B, transitions pro (`xfade`) aléatoires. |
| 🤖 **Avatar aléatoire** | Insère automatiquement une vidéo "mascotte" dans une scène du milieu pour l'identité de marque. |

---

## 📂 Structure du projet

```text
Automated-YT-Shorts-AI/
│
├── .github/workflows/           # ☁️ Règles d'automatisation cloud
│   ├── generator_video.yml      # Génération à 06h00 et 18h00 UTC
│   └── tiktok_bot.yml           # Publication TikTok à 12h00 et 19h00 UTC
│
├── assets/                      # Fichiers médias locaux
│   ├── temp/                    # Fichiers intermédiaires
│   ├── final/                   # 🏆 Vidéo finale
│   └── avatar/                  # ⚠️ Placer votre vidéo avatar ici (avatars.mp4)
│
├── modules/                     # Logique principale
│   ├── brain.py                 # Scriptwriter IA
│   ├── audio.py                 # Générateur de voix (edge-tts)
│   ├── asset_manager.py         # Téléchargeur Pexels (logique Dual-Visual)
│   └── composer.py              # Monteur vidéo FFmpeg (montage & transitions)
│
├── main.py                      # Moteur principal de génération vidéo
├── publish.py                   # Bot de publication TikTok (API Zernio + Hugging Face)
├── constants.py                 # Variables globales & URLs
└── requirements.txt             # Dépendances Python
```

---

## 🛠️ Prérequis & clés API

Pour faire tourner ce pipeline dans le cloud, il vous faut des comptes et clés API pour :

- **Google Gemini API Key** (ou **Groq API Key**) — génération de scripts
- **Pexels API Key** (gratuite) — recherche/téléchargement de vidéos stock
- **Hugging Face Token** (`HF_TOKEN`) — upload/lecture des vidéos
- **Zernio API Key** + **TikTok Account ID** — bot de publication

*(Optionnel pour du dev local)* : Python 3.10+ et FFmpeg installés sur votre machine.

---

## 🚀 Installation & automatisation cloud (GitHub Actions)

Oubliez l'exécution locale, voici comment configurer le pipeline 100% automatisé :

### 1. Fork ou clone du dépôt
Poussez ce code vers votre propre dépôt GitHub privé.

### 2. Configuration des secrets GitHub
Rendez-vous dans **Settings > Secrets and variables > Actions** de votre dépôt, puis ajoutez les secrets suivants :

- `GEMINI_API_KEY`
- `GROQ_API_KEY` *(si utilisé)*
- `PEXELS_API_KEY`
- `HF_TOKEN`
- `ZERNIO_API_KEY`
- `TIKTOK_ACCOUNT_ID`

### 3. Ajout de votre avatar
Uploadez votre fichier `avatars.mp4` dans le dossier `assets/avatar/` et poussez-le sur votre dépôt.

### 4. Lancement des workflows
Dans l'onglet **Actions** de votre dépôt GitHub :

- Cliquez sur **Générateur de Vidéos IA** → **Run workflow** pour générer une vidéo manuellement.
- Cliquez sur **Bot Auto-Publication TikTok** → **Run workflow** pour publier la dernière vidéo (Hugging Face → TikTok).

> **Note :** grâce aux fichiers `.yml`, le pipeline tourne ensuite automatiquement selon le planning : génération à 6h/18h, publication à 12h/19h.

---

## 🧩 Détail du nouveau module

### `publish.py` (Le Publisher)

- **Entrée :** se connecte à l'API Hugging Face pour trouver le dernier `.mp4` généré aujourd'hui.
- **Logique :** extrait un titre propre du nom de fichier pour créer une légende engageante avec hashtags. Se protège du double-post via une logique horaire.
- **Sortie :** envoie le payload à l'API Zernio, déclenchant l'upload direct sur TikTok avec la mention IA activée (`video_made_with_ai: True`).

---

## ⚠️ Dépannage

**Q : Le workflow GitHub Actions échoue sur `publish.py` avec une erreur 409.**
**R :** C'est normal ! Zernio renvoie une erreur `409 Conflict` si la même vidéo a déjà été publiée dans les dernières 24h. Le script intercepte cette erreur pour éviter le spam sur votre compte.

**Q : Erreur "Avatar file missing".**
**R :** Vérifiez que la structure de dossier est exactement `assets/avatar/avatars.mp4` dans votre dépôt GitHub.

**Q : La vidéo est noire ou corrompue (erreur `0x80004005` sur Windows).**
**R :** Généralement un problème de codec Windows. Le `composer.py` mis à jour force `pix_fmt='yuv420p'`. Essayez d'ouvrir le fichier avec VLC Media Player, ou laissez TikTok le traiter nativement.

---

## 📜 Licence

Projet open-source. Libre à vous de le modifier et de construire votre propre empire d'automatisation !
