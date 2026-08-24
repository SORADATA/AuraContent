import json
import os
import statistics
from datetime import datetime


class PerformanceLearner:
    def __init__(self, filepath=None):
        self.filepath = filepath or os.path.join(
            os.getcwd(), "assets", "performance_history.json"
        )
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)

    def _load(self):
        if not os.path.exists(self.filepath):
            return []

        try:
            with open(self.filepath, "r", encoding="utf-8") as file:
                data = json.load(file)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save(self, data):
        with open(self.filepath, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)

    def record(self, title, topic, hook_pattern=None, duration=None, views=None, 
               avg_watch_time=None, completion_rate=None, likes=None, 
               comments=None, shares=None, follows=None):
        
        data = self._load()

        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "title": title,
            "topic": topic,
            "hook_pattern": hook_pattern,
            "duration": duration,
            "views": views,
            "avg_watch_time": avg_watch_time,
            "completion_rate": completion_rate,
            "likes": likes,
            "comments": comments,
            "shares": shares,
            "follows": follows,
        }

        data.append(entry)

        # On garde un historique raisonnable (les 500 dernières vidéos)
        data = data[-500:]
        self._save(data)

    def _safe_float(self, value):
        try:
            return float(value)
        except Exception:
            return None

    def analyze(self):
        data = self._load()
        if not data:
            return {}

        grouped = {}
        for row in data:
            pattern = row.get("hook_pattern") or "unknown"
            grouped.setdefault(pattern, []).append(row)

        result = {}
        for pattern, rows in grouped.items():
            completion = [self._safe_float(x.get("completion_rate")) for x in rows]
            completion = [x for x in completion if x is not None]

            watch = [self._safe_float(x.get("avg_watch_time")) for x in rows]
            watch = [x for x in watch if x is not None]

            shares = [self._safe_float(x.get("shares")) for x in rows]
            shares = [x for x in shares if x is not None]

            result[pattern] = {
                "videos": len(rows),
                "avg_completion": statistics.mean(completion) if completion else 0,
                "avg_watch_time": statistics.mean(watch) if watch else 0,
                "avg_shares": statistics.mean(shares) if shares else 0,
            }

        return result

    def get_best_patterns(self):
        analysis = self.analyze()
        if not analysis:
            return []

        ranked = []
        for pattern, stats in analysis.items():
            # Scoring pondéré orienté Rétention et Viralité
            score = (
                stats["avg_completion"] * 0.55
                + stats["avg_watch_time"] * 0.30
                + stats["avg_shares"] * 0.15
            )
            ranked.append((score, pattern))

        ranked.sort(reverse=True)
        return [pattern for _, pattern in ranked]
