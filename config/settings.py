# config/settings.py
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"

# Configuration par API / Fournisseur
GEMINI_CONFIG = {
    "text": "gemini-3.6-flash",
    "voice": "gemini-2.5-flash-preview-tts"
}

GROQ_MODELS = [
    "openai/gpt-oss-20b",
    "llama-3.3-70b-specdec"
]

OPENROUTER_ROUTING = [
    "meta-llama/llama-3.3-70b-instruct",
    "google/gemma-3-27b-it:free",
]

AI_MENTION_PATTERNS = [
    r"intelligence\s+artificielle", r"\bIA\b", r"\bl'IA\b",
    r"artificial\s+intelligence", r"\bl'algorithme\b", r"\bchatgpt\b",
    r"\bgroq\b", r"\bgemini\b", r"genere[e]?\s+par\s+l'?ia",
]
ACCENTED_CHARS = "éèêëàâäùûüçîïôœ"
_TITLE_STOPWORDS = {"de", "du", "des", "la", "le", "les", "d", "l", "et", "en", "au", "aux", "un", "une", "the", "of"}
