"""
hook_tracker.py
================
Bandit manchot (multi-armed bandit) applique a la selection de hooks.

Principe :
- Chaque "pattern" de hook (question, choc, statistique, etc.) est un bras.
- On garde en memoire quel pattern a ete utilise pour chaque titre de video.
- Au run suivant, on recroise cet historique avec les stats Zernio (vues,
  likes) pour calculer un score moyen par pattern.
- select_hook() applique une strategie epsilon-greedy : la plupart du temps
  on exploite le meilleur pattern connu, mais on explore aleatoirement une
  fraction du temps (epsilon) pour continuer a decouvrir/confirmer la
  performance des autres patterns et eviter de converger trop vite sur un
  optimum local.

Persistance : l'historique (titre <-> pattern) est stocke dans un petit
fichier JSON pousse sur le dataset Hugging Face deja utilise pour l'upload
video (soradata/AIShortvideos), car les runners GitHub Actions sont
ephemeres et perdent le disque local entre deux executions.
"""

import os
import json
import random
import tempfile
import difflib

try:
    from huggingface_hub import hf_hub_download, upload_file
    HF_AVAILABLE = True
except ImportError:
    HF_AVAILABLE = False

HF_DATASET_REPO = os.getenv("HF_DATASET_REPO", "soradata/AIShortvideos")
HF_HISTORY_PATH_IN_REPO = "meta/hook_history.json"
HF_TOKEN = os.getenv("HF_TOKEN")

EPSILON = float(os.getenv("HOOK_BANDIT_EPSILON", "0.2"))  # 20% exploration


def _normalize_title(title):
    return " ".join(str(title or "").lower().split())


def load_hook_history():
    """Recupere l'historique {titre, pattern} depuis le dataset HF.
    Retourne une liste vide si indisponible (ne doit jamais casser le pipeline)."""
    if not HF_AVAILABLE:
        print("⚠️ huggingface_hub indisponible, historique des hooks desactive.")
        return []

    try:
        local_path = hf_hub_download(
            repo_id=HF_DATASET_REPO,
            repo_type="dataset",
            filename=HF_HISTORY_PATH_IN_REPO,
            token=HF_TOKEN,
        )
        with open(local_path, "r", encoding="utf-8") as f:
            history = json.load(f)
        if isinstance(history, list):
            return history
        return []
    except Exception as e:
        print(f"ℹ️ Aucun historique de hooks trouve (premiere execution ?) : {e}")
        return []


def record_hook_usage(video_title, pattern):
    """Ajoute une entree {titre, pattern} a l'historique et la republie sur HF.
    Echec silencieux (non bloquant) si HF est indisponible."""
    if not HF_AVAILABLE or not pattern:
        return False

    history = load_hook_history()
    history.append({"title": video_title, "pattern": pattern})

    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as tmp:
            json.dump(history, tmp, ensure_ascii=False, indent=2)
            tmp_path = tmp.name

        upload_file(
            path_or_fileobj=tmp_path,
            path_in_repo=HF_HISTORY_PATH_IN_REPO,
            repo_id=HF_DATASET_REPO,
            repo_type="dataset",
            token=HF_TOKEN,
        )
        os.remove(tmp_path)
        print(f"📊 Historique des hooks mis a jour ({pattern}) sur Hugging Face.")
        return True
    except Exception as e:
        print(f"⚠️ Impossible de sauvegarder l'historique des hooks : {e}")
        return False


def _min_max_normalize(values):
    if not values:
        return {}
    lo, hi = min(values), max(values)
    if hi == lo:
        return {v: 0.5 for v in values}
    return {v: (v - lo) / (hi - lo) for v in values}


def compute_pattern_scores(previous_stats_list, history):
    """
    Recroise l'historique (titre -> pattern) avec les stats Zernio
    (titre -> vues/likes) pour produire un score moyen par pattern.

    Score composite par video = 0.5 * vues_normalisees + 0.5 * likes_normalises
    (normalisation min-max sur l'ensemble des stats disponibles).
    """
    if not previous_stats_list or not history:
        return {}

    stats_by_title = {
        _normalize_title(s.get("title")): s
        for s in previous_stats_list
        if isinstance(s, dict) and s.get("title")
    }

    views_all = [float(s.get("views", 0) or 0) for s in previous_stats_list if isinstance(s, dict)]
    likes_all = [float(s.get("likes", 0) or 0) for s in previous_stats_list if isinstance(s, dict)]
    views_norm_map = _min_max_normalize(views_all)
    likes_norm_map = _min_max_normalize(likes_all)

    pattern_scores = {}
    pattern_counts = {}

    for entry in history:
        title_key = _normalize_title(entry.get("title"))
        pattern = entry.get("pattern")
        stat = stats_by_title.get(title_key)
        if not stat or not pattern:
            continue

        views = float(stat.get("views", 0) or 0)
        likes = float(stat.get("likes", 0) or 0)
        score = 0.5 * views_norm_map.get(views, 0.0) + 0.5 * likes_norm_map.get(likes, 0.0)

        pattern_scores[pattern] = pattern_scores.get(pattern, 0.0) + score
        pattern_counts[pattern] = pattern_counts.get(pattern, 0) + 1

    return {
        pattern: pattern_scores[pattern] / pattern_counts[pattern]
        for pattern in pattern_scores
    }


def select_hook(hooks, pattern_scores=None, epsilon=EPSILON):
    """
    Strategie epsilon-greedy :
    - Avec probabilite epsilon (defaut 20%) : exploration -> choix aleatoire
      parmi les 5 hooks generes, pour continuer a tester tous les patterns.
    - Sinon (80% du temps) : exploitation -> on choisit, parmi les hooks
      generes, celui dont le pattern a le meilleur score historique connu.
      Si aucun pattern connu ne correspond aux hooks generes, on retombe
      sur un choix aleatoire.
    """
    if not hooks:
        return None

    do_explore = random.random() < epsilon

    if not do_explore and pattern_scores:
        scored_candidates = [
            (h, pattern_scores[h.get("pattern")])
            for h in hooks
            if h.get("pattern") in pattern_scores
        ]
        if scored_candidates:
            best_hook, best_score = max(scored_candidates, key=lambda x: x[1])
            print(
                f"🎯 Hook selectionne par exploitation (pattern: "
                f"{best_hook.get('pattern')}, score historique: {best_score:.3f})"
            )
            return best_hook

    chosen = random.choice(hooks)
    reason = "exploration forcee" if do_explore else "pas de score historique disponible"
    print(f"🎲 Hook selectionne aleatoirement ({reason}), pattern: {chosen.get('pattern', '?')}")
    return chosen


def is_topic_redundant(new_title, history, threshold=0.55):
    """
    Compare le nouveau titre généré avec l'historique de Hugging Face.
    Si le ratio de similarité dépasse le seuil, la vidéo est bloquée.
    """
    if not history:
        return False
        
    new_norm = _normalize_title(new_title)
    
    for entry in history:
        old_title = entry.get("title", "")
        old_norm = _normalize_title(old_title)
        
        # Calcul du ratio de ressemblance entre 0.0 et 1.0
        similarity = difflib.SequenceMatcher(None, new_norm, old_norm).ratio()
        
        # Mots-clés discriminants (ex: si le lieu exact est déjà dans un ancien titre)
        common_words = set(new_norm.split()) & set(old_norm.split())
        critical_overlap = len(common_words) > 3 # Plus de 3 mots identiques
        
        if similarity > threshold or critical_overlap:
            print(f"🚫 BLOCAGE QUALITÉ : '{new_title}' est trop similaire à '{old_title}' (Score: {similarity:.2f})")
            return True
            
    return False
