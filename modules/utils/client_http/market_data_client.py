"""
Client Alpha Vantage pour alimenter ContentBrain avec des donnees de marche
reelles (top gainers/losers + sentiment de news).

Cle API attendue dans .env (local) ou GitHub Secrets (CI) sous le nom :
    ALPHA_VANTAGE_API_KEY

Free tier Alpha Vantage : 25 requetes / jour, 5 requetes / minute.
Ce module met en cache le resultat du jour dans un fichier JSON pour
ne consommer qu'un minimum d'appels, meme si tu relances ton script
plusieurs fois dans la journee.
"""

import os
import json
import requests
from datetime import date
from pathlib import Path
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2] if "modules" in str(Path(__file__).resolve()) else Path(__file__).resolve().parent
ENV_PATH = PROJECT_ROOT / ".env"
load_dotenv(dotenv_path=ENV_PATH)

API_KEY = os.getenv("VANTAGE_API_KEY") or os.getenv("VANTAGE_API_KEY")

BASE_URL = "https://www.alphavantage.co/query"
CACHE_PATH = PROJECT_ROOT / "market_signals_cache.json"

REQUEST_TIMEOUT = 15


def _is_rate_limited_or_invalid(data):
    if not isinstance(data, dict):
        return False
    if "Note" in data:
        print(f"⚠️ Alpha Vantage rate limit atteint : {data['Note']}")
        return True
    if "Information" in data:
        print(f"⚠️ Alpha Vantage info/erreur : {data['Information']}")
        return True
    if "Error Message" in data:
        print(f"⚠️ Alpha Vantage erreur : {data['Error Message']}")
        return True
    return False


def _fetch(params):
    if not API_KEY:
        print("⚠️ ALPHA_VANTAGE_API_KEY manquant dans .env / secrets. Aucune donnee recuperee.")
        return None

    params = {**params, "apikey": API_KEY}

    try:
        response = requests.get(BASE_URL, params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as e:
        print(f"⚠️ Erreur reseau Alpha Vantage : {e}")
        return None
    except ValueError:
        print("⚠️ Reponse Alpha Vantage non-JSON.")
        return None

    if _is_rate_limited_or_invalid(data):
        return None

    return data


def get_top_gainers_losers(limit=5):
    """Retourne les top gainers/losers US du jour via TOP_GAINERS_LOSERS."""
    data = _fetch({"function": "TOP_GAINERS_LOSERS"})
    if not data:
        return None

    def _parse(entries):
        parsed = []
        for entry in entries[:limit]:
            try:
                parsed.append({
                    "ticker": entry.get("ticker"),
                    "price": entry.get("price"),
                    "change_percent": entry.get("change_percentage", "").replace("%", ""),
                })
            except (AttributeError, TypeError):
                continue
        return parsed

    top_gainers = _parse(data.get("top_gainers", []))
    top_losers = _parse(data.get("top_losers", []))

    if not top_gainers and not top_losers:
        return None

    return {"top_gainers": top_gainers, "top_losers": top_losers}


def get_news_sentiment(topics="financial_markets", limit=30):
    """
    Recupere des news financieres recentes et deduit un sentiment global
    simple (bullish / bearish / neutre) a partir du score moyen Alpha Vantage.
    """
    data = _fetch({
        "function": "NEWS_SENTIMENT",
        "topics": topics,
        "limit": limit,
        "sort": "LATEST",
    })
    if not data:
        return None

    feed = data.get("feed", [])
    if not feed:
        return None

    scores = []
    headlines = []
    for article in feed:
        try:
            score = float(article.get("overall_sentiment_score", 0))
            scores.append(score)
        except (TypeError, ValueError):
            continue

        title = article.get("title")
        if title:
            headlines.append(title)

    if not scores:
        return None

    avg_score = sum(scores) / len(scores)

    if avg_score >= 0.15:
        sentiment_label = "haussier (bullish)"
    elif avg_score <= -0.15:
        sentiment_label = "baissier (bearish)"
    else:
        sentiment_label = "neutre / incertain"

    return {
        "sentiment": sentiment_label,
        "sentiment_score": round(avg_score, 3),
        "sample_headlines": headlines[:5],
    }


def _load_cache():
    if not CACHE_PATH.exists():
        return None

    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            cache = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    if cache.get("date") != str(date.today()):
        return None

    return cache.get("signals")


def _save_cache(signals):
    cache = {"date": str(date.today()), "signals": signals}
    try:
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"⚠️ Impossible d'ecrire le cache marche : {e}")


def get_market_signals(use_cache=True, force_refresh=False):
    """
    Point d'entree principal pour ContentBrain.
    Retourne un dict compatible avec _format_market_instruction() :
    {
        "sentiment": str,
        "top_gainers": [...],
        "top_losers": [...],
        "politician_trades": []  # non disponible via Alpha Vantage
    }
    """
    if use_cache and not force_refresh:
        cached = _load_cache()
        if cached:
            print("📦 Signaux de marche recuperes depuis le cache du jour.")
            return cached

    if not API_KEY:
        print("⚠️ Pas de cle Alpha Vantage : ContentBrain fonctionnera sans donnees de marche live.")
        return None

    print("📡 Appel Alpha Vantage : top gainers/losers...")
    gainers_losers = get_top_gainers_losers() or {}

    print("📡 Appel Alpha Vantage : sentiment des news financieres...")
    news_sentiment = get_news_sentiment() or {}

    signals = {
        "sentiment": news_sentiment.get("sentiment"),
        "sentiment_score": news_sentiment.get("sentiment_score"),
        "top_gainers": gainers_losers.get("top_gainers", []),
        "top_losers": gainers_losers.get("top_losers", []),
        "politician_trades": [],
    }

    if not signals["sentiment"] and not signals["top_gainers"] and not signals["top_losers"]:
        print("⚠️ Aucune donnee de marche recuperee (quota atteint ou cle invalide).")
        return None

    _save_cache(signals)
    return signals


if __name__ == "__main__":
    signals = get_market_signals(force_refresh=True)

    if signals:
        print("\n=== Signaux de marche du jour ===")
        print(json.dumps(signals, indent=2, ensure_ascii=False))
    else:
        print("\nAucun signal recupere. Verifie ta cle ALPHA_VANTAGE_API_KEY.")
