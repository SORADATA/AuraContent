# 🎬 AutoShorts AI: The Automated Faceless Video Generator

**AutoShorts AI** is a fully automated Python pipeline that creates viral-style "Faceless" YouTube Shorts and TikToks from a single topic. It handles the entire production chain: researching, scriptwriting, voiceover generation, stock footage sourcing, and advanced video editing with transitions and avatar injection.

---

## ✨ Key Features

- **🧠 Intelligent Scriptwriting:** Uses **Google Gemini 2.0 Flash** to write engaging, "Edutainment" style scripts (Vox/Kurzgesagt style) with strict storytelling structures (Hook → Context → Mechanism → Twist).
- **🗣️ Human-Like Voiceovers:** Integrated with **Suno Bark** (via Google Colab/Ngrok) for high-quality, expressive AI narration. Includes "Influencer Mode" for dynamic intonation.
- **🎞️ Dual-Visual System:** Automatically searches and downloads **two distinct stock videos** per scene from **Pexels**, creating a dynamic "A/B Split" visual style to maximize viewer retention.
- **✂️ Advanced FFmpeg Editing:**
- **Smart Trimming:** Syncs video perfectly to audio duration.
- **A/B Splitting:** Cuts every scene in half, switching visuals mid-sentence.
- **Pro Transitions:** Randomly applies `xfade` (fade, slide, wipes) between scenes.
- **Silence Removal:** Automatically trims dead air from AI voice generation.

- **🤖 Random Avatar Injection:** Automatically inserts a custom "Avatar/Mascot" video into a random middle scene to build channel brand identity.
- **🪟 Windows Ready:** Includes specific FFmpeg flags (`yuv420p`, `faststart`) to prevent corruption errors (`0x80004005`) on Windows Media Player.

---

## 📂 Project Structure

```text
Automated-YT-Shorts-AI/
│
├── assets/                  # Stores all media files
│   ├── audio_clips/         # Generated voiceovers (.wav)
│   ├── video_clips/         # Downloaded stock footage (.mp4)
│   ├── temp/                # Intermediate processing files
│   ├── final/               # 🏆 The Final Output Video lives here
│   └── avatar/              # ⚠️ PUT YOUR AVATAR VIDEO HERE
│       └── Professional_Girl_Animation_Video_Generation.mp4
│
├── modules/                 # Core Logic Modules
│   ├── brain.py             # AI Scriptwriter (Gemini)
│   ├── audio.py             # Voice Generator (Bark Client)
│   ├── asset_manager.py     # Pexels Downloader (Dual-Visual logic)
│   └── composer.py          # FFmpeg Video Editor (Stitching & Transitions)
│
├── main.py                  # Entry point (Orchestrator)
├── test_audio.py            # Diagnostic tool for Bark connection
└── requirements.txt         # Python dependencies

```

---

## 🛠️ Prerequisites

1. **Python 3.10+** installed.
2. **FFmpeg** installed and added to your system PATH.

- _Windows:_ `winget install ffmpeg` (or download from [ffmpeg.org](https://ffmpeg.org/download.html)).
- _Verify:_ Type `ffmpeg -version` in your terminal.

3. **API Keys:**

- **Google Gemini API Key** (Free tier available).
- **Pexels API Key** (Free).
- **Ngrok Auth Token** (If running Bark on Colab).

---

## 🚀 Installation

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/AutoShorts-AI.git
cd AutoShorts-AI

```

### 2. Install Dependencies

```bash
pip install -r requirements.txt

```

_(If `requirements.txt` is missing, install manually: `pip install google-generativeai requests ffmpeg-python mutagen colorama`)_

### 3. Environment Setup

Create the required folders and add your avatar:

1. Create folder: `assets/avatar`
2. Place your avatar video inside and name it: `Professional_Girl_Animation_Video_Generation.mp4`

### 4. Configure API Keys

You can set them in your environment variables or hardcode them (temporarily) in the modules:

- `modules/brain.py` → `genai.configure(api_key="YOUR_GEMINI_KEY")`
- `modules/asset_manager.py` → `self.api_key = "YOUR_PEXELS_KEY"`
- `modules/audio.py` → Update `raw_url` with your active Ngrok/Colab link.

---

## 🎮 How to Run

### Step 1: Start the Audio Server (Bark)

Since Bark requires a GPU, we run it on Google Colab.

1. Open the **Colab Notebook** provided for this project.
2. Paste your Ngrok Token.
3. Run the cell.
4. Copy the `https://xxxx.ngrok-free.app` URL.
5. Paste this URL into `modules/audio.py` inside the `AudioEngine` class.

### Step 2: Test Connection (Optional)

Run the test script to ensure your local machine can talk to the Cloud GPU.

```bash
python test_audio.py

```

_If you see `✅ SUCCESS`, you are ready._

### Step 3: Generate Video

Run the main script:

```bash
python main.py

```

1. Enter a topic (e.g., _"The Mystery of the Pyramids"_).
2. Wait for the AI to write the script, generate audio, download stock footage, and edit the video.
3. The final video will be saved in `assets/final/final_short.mp4`.

---

## 🧩 Module Breakdown

### `brain.py` ( The Writer)

- **Input:** Topic string.
- **Logic:** Prompts Gemini to create an 8-9 scene JSON script. It asks for **two** visual keywords per scene (`visual_1`, `visual_2`) to enable the A/B split effect.

### `audio.py` (The Voice)

- **Input:** Text script.
- **Logic:** Sends text to the Colab server. Includes a "Confidence" setting (`text_temp=0.7`) to make the voice sound like an influencer.
- **Post-Processing:** Uses FFmpeg to trim silence and boost volume (2x).

### `asset_manager.py` (The Librarian)

- **Input:** Visual keywords.
- **Logic:** Searches Pexels for **Portrait (9:16)** videos. Downloads pairs of videos for every scene. Handles fallbacks (if Video B is missing, reuse Video A).

### `composer.py` (The Editor)

- **Input:** Audio files + Video files.
- **Logic:**
- **Scene Processing:** Cuts the scene duration in half. Plays Video A for the first half, Video B for the second half.
- **Avatar Injection:** Identifies a random "middle" scene (not hook/outro) and replaces the stock footage with your Avatar loop.
- **Stitching:** Merges all scenes using `xfade` transitions (wipes, slides).
- **Rendering:** Exports as `yuv420p` H.264 MP4 with `faststart` flags for maximum compatibility.

---

## ⚠️ Troubleshooting

**Q: The video is black or corrupt (0x80004005 error).**

- **Fix:** This is usually a Windows codec issue. The updated `composer.py` forces `pix_fmt='yuv420p'`. Try opening the file with VLC Media Player.

**Q: "Avatar file missing" error.**

- **Fix:** Altough not needed, Ensure your folder structure is exactly `assets/avatar/avatar.mp4`.

**Q: The audio is silent or fails.**

- **Fix:** Your Ngrok tunnel likely expired. Restart the Colab cell and update the URL in `audio.py`.

**Q: FFmpeg error "Exec format error" or "not found".**

- **Fix:** Ensure FFmpeg is installed and accessible from your command line.

---

## 📜 License

This project is open-source. Feel free to modify and build your own automation empire!
