# config/settings.py
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"

GEMINI_MODEL_VOICE = "gemini-2.5-flash-preview-tts"  # Voix gemini
GEMINI_MODEL = "gemini-3.6-flash"
GROQ_MODEL = "openai/gpt-oss-20b"
# GROQ_MODEL = "llama-3.3-70b-specdec"
OPENROUTER_FALLBACK_MODEL_1 = "meta-llama/llama-3.3-70b-instruct"
OPENROUTER_FALLBACK_MODEL_2 = "google/gemma-3-27b-it:free"
