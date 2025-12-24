# 🎬 Automated YouTube Shorts Generator

> _Infinite content, zero manual editing._

Hi! This is a Python-based automation tool that generates engaging, "faceless" YouTube Shorts from scratch. It uses AI to think up ideas, writes a script, finds relevant stock footage, generates a voiceover, and stitches it all together with pro-level transitions.

It’s built to be modular, so you can swap out the "Brain" (Gemini) or the "Assets" (Pexels) if you want to customize it later.

---

## ⚡ Features

- **🧠 The Brain:** Uses **Google Gemini 2.0 Flash** to research viral topics and write 3rd-person narrative scripts (8-9 scenes).
- **🗣️ The Voice:** Uses **Edge-TTS** (Microsoft Edge's Neural engine) for natural, non-robotic voiceovers. No paid API keys needed for this part!
- **🎥 The Visuals:** Automatically searches **Pexels** for high-quality, portrait-mode (9:16) stock footage based on script keywords.
- **✂️ The Editor:** Uses **FFmpeg** to trim clips, resize them, and apply randomized transitions (Wipes, Slides, Fades) between scenes.
- **🛡️ Robust:** Includes retry logic for API calls so it doesn't crash if the internet blinks.

---

## 🛠️ Prerequisites

Before you run this, you need a few things installed:

1.  **Python 3.10+**
2.  **FFmpeg (2020 version or newer)**
    - ⚠️ **CRITICAL:** Do not use the old 2013 builds. This project uses `xfade` filters for transitions, which only exist in modern FFmpeg versions (4.3+).
    - [Download Modern FFmpeg Here](https://www.gyan.dev/ffmpeg/builds/)
3.  **API Keys:**
    - **Google Gemini API Key** (Free tier available via Google AI Studio).
    - **Pexels API Key** (Free, instant signup).

---

## 🚀 Installation

1.  **Clone the repo** (or download the files):

    ```bash
    git clone [https://github.com/SaarD00/Automated-YT-Shorts-AI]
    cd Automated-YT-Shorts-AI
    ```

2.  **Install Python dependencies:**

    ```bash
    pip install -r requirements.txt
    ```

3.  **Set up your Environment:**
    Create a file named `.env` in the root folder and add your keys:
    ```ini
    GEMINI_API_KEY=your_gemini_key_here
    PEXELS_API_KEY=your_pexels_key_here
    ```

---

## 🏃‍♂️ Usage

Just run the main script. It handles everything end-to-end.

```bash
python main.py
```
