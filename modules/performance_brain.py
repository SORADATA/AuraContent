import json
import os
import statistics
import math
import re
from datetime import datetime, timezone


class PerformanceLearner:
    """
    Moteur d'apprentissage des performances du pipeline vidéo.

    Objectif :
        publication
            ↓
        statistiques
            ↓
        normalisation
            ↓
        scoring
            ↓
        détection des patterns gagnants
            ↓
        recommandations
            ↓
        prochain script

    Le système ne prétend pas prédire les 10K vues.
    Il cherche à identifier les caractéristiques qui fonctionnent
    réellement sur l'historique disponible.
    """

    MAX_HISTORY = 500

    # ------------------------------------------------------------
    # POIDS DU SCORE GLOBAL
    # ------------------------------------------------------------

    WEIGHTS = {
        "completion": 0.35,
        "watch_time": 0.25,
        "shares": 0.18,
        "likes": 0.10,
        "comments": 0.07,
        "follows": 0.05,
    }

    # Minimum de vidéos avant de considérer un pattern comme fiable.
    MIN_PATTERN_SAMPLES = 2

    # ------------------------------------------------------------
    # INITIALISATION
    # ------------------------------------------------------------

    def __init__(self, filepath=None):
        self.filepath = filepath or os.path.join(
            os.getcwd(),
            "assets",
            "performance_history.json",
        )

        os.makedirs(
            os.path.dirname(self.filepath),
            exist_ok=True,
        )

    # ------------------------------------------------------------
    # STOCKAGE
    # ------------------------------------------------------------

    def _load(self):
        if not os.path.exists(self.filepath):
            return []

        try:
            with open(
                self.filepath,
                "r",
                encoding="utf-8",
            ) as file:
                data = json.load(file)

            if isinstance(data, list):
                return data

        except Exception as e:
            print(
                f"⚠️ PerformanceLearner : "
                f"historique illisible : {e}"
            )

        return []

    def _save(self, data):
        try:
            with open(
                self.filepath,
                "w",
                encoding="utf-8",
            ) as file:
                json.dump(
                    data,
                    file,
                    ensure_ascii=False,
                    indent=2,
                )

            return True

        except Exception as e:
            print(
                f"⚠️ Impossible de sauvegarder "
                f"l'historique performance : {e}"
            )
            return False

    # ------------------------------------------------------------
    # UTILITAIRES NUMÉRIQUES
    # ------------------------------------------------------------

    def _safe_float(self, value):
        if value is None:
            return None

        if isinstance(value, bool):
            return None

        try:
            if isinstance(value, str):
                value = (
                    value
                    .replace("%", "")
                    .replace(",", ".")
                    .strip()
                )

            result = float(value)

            if math.isnan(result) or math.isinf(result):
                return None

            return result

        except Exception:
            return None

    def _mean(self, values):
        clean = [
            self._safe_float(value)
            for value in values
        ]

        clean = [
            value
            for value in clean
            if value is not None
        ]

        if not clean:
            return 0.0

        return statistics.mean(clean)

    def _median(self, values):
        clean = [
            self._safe_float(value)
            for value in values
        ]

        clean = [
            value
            for value in clean
            if value is not None
        ]

        if not clean:
            return 0.0

        return statistics.median(clean)

    def _clamp(self, value, minimum=0.0, maximum=1.0):
        return max(
            minimum,
            min(maximum, value),
        )

    def _normalize_rate(self, value):
        """
        Convertit :
            0.72 -> 0.72
            72   -> 0.72
        """

        value = self._safe_float(value)

        if value is None:
            return None

        if value > 1.0:
            value /= 100.0

        return self._clamp(value)

    # ------------------------------------------------------------
    # NORMALISATION DES STATISTIQUES
    # ------------------------------------------------------------

    def _normalize_row(self, row):
        """
        Rend les statistiques cohérentes même si Zernio/API
        fournit différentes unités.
        """

        normalized = dict(row)

        completion = self._normalize_rate(
            row.get("completion_rate")
        )

        likes = self._safe_float(
            row.get("likes")
        )

        comments = self._safe_float(
            row.get("comments")
        )

        shares = self._safe_float(
            row.get("shares")
        )

        follows = self._safe_float(
            row.get("follows")
        )

        views = self._safe_float(
            row.get("views")
        )

        watch_time = self._safe_float(
            row.get("avg_watch_time")
        )

        duration = self._safe_float(
            row.get("duration")
        )

        normalized["completion_rate_normalized"] = completion
        normalized["likes"] = likes
        normalized["comments"] = comments
        normalized["shares"] = shares
        normalized["follows"] = follows
        normalized["views"] = views
        normalized["avg_watch_time"] = watch_time
        normalized["duration"] = duration

        # --------------------------------------------------------
        # Taux d'engagement
        # --------------------------------------------------------

        if views and views > 0:
            normalized["like_rate"] = (
                likes / views
                if likes is not None
                else None
            )

            normalized["comment_rate"] = (
                comments / views
                if comments is not None
                else None
            )

            normalized["share_rate"] = (
                shares / views
                if shares is not None
                else None
            )

            normalized["follow_rate"] = (
                follows / views
                if follows is not None
                else None
            )

        else:
            normalized["like_rate"] = None
            normalized["comment_rate"] = None
            normalized["share_rate"] = None
            normalized["follow_rate"] = None

        # --------------------------------------------------------
        # Rétention reconstruite si nécessaire
        # --------------------------------------------------------

        if (
            normalized["completion_rate_normalized"]
            is None
            and watch_time is not None
            and duration
            and duration > 0
        ):
            normalized["completion_rate_normalized"] = self._clamp(
                watch_time / duration
            )

        return normalized

    # ------------------------------------------------------------
    # SCORE INDIVIDUEL
    # ------------------------------------------------------------

    def _compute_video_score(
        self,
        row,
        dataset=None,
    ):
        """
        Calcule un score 0-100.

        Les métriques absolues d'engagement sont comparées
        à l'historique pour éviter qu'une vidéo avec beaucoup
        de vues domine artificiellement toutes les autres.
        """

        normalized = self._normalize_row(row)

        if dataset is None:
            dataset = self._load()

        normalized_rows = [
            self._normalize_row(item)
            for item in dataset
        ]

        def percentile_score(
            field,
            value,
        ):
            if value is None:
                return None

            values = []

            for item in normalized_rows:
                candidate = self._safe_float(
                    item.get(field)
                )

                if candidate is not None:
                    values.append(candidate)

            if len(values) < 2:
                return None

            below_or_equal = sum(
                1
                for candidate in values
                if candidate <= value
            )

            percentile = (
                below_or_equal / len(values)
            )

            return self._clamp(percentile)

        components = []

        metrics = [
            (
                "completion_rate_normalized",
                self.WEIGHTS["completion"],
            ),
            (
                "avg_watch_time",
                self.WEIGHTS["watch_time"],
            ),
            (
                "share_rate",
                self.WEIGHTS["shares"],
            ),
            (
                "like_rate",
                self.WEIGHTS["likes"],
            ),
            (
                "comment_rate",
                self.WEIGHTS["comments"],
            ),
            (
                "follow_rate",
                self.WEIGHTS["follows"],
            ),
        ]

        total_weight = 0.0

        for field, weight in metrics:
            value = normalized.get(field)

            if value is None:
                continue

            percentile = percentile_score(
                field,
                value,
            )

            if percentile is None:
                # Si le dataset est encore trop petit,
                # on utilise une valeur directement normalisée.
                if field == "completion_rate_normalized":
                    percentile = value

                elif field == "avg_watch_time":
                    duration = normalized.get(
                        "duration"
                    )

                    if duration and duration > 0:
                        percentile = self._clamp(
                            value / duration
                        )
                    else:
                        percentile = 0.5

                else:
                    percentile = 0.5

            components.append(
                percentile * weight
            )

            total_weight += weight

        if total_weight <= 0:
            return 0.0

        score = (
            sum(components)
            / total_weight
        ) * 100

        return round(
            self._clamp(score, 0, 100),
            2,
        )

    # ------------------------------------------------------------
    # ENREGISTREMENT
    # ------------------------------------------------------------

    def record(
        self,
        title,
        topic,
        hook_pattern=None,
        duration=None,
        views=None,
        avg_watch_time=None,
        completion_rate=None,
        likes=None,
        comments=None,
        shares=None,
        follows=None,
        hook_text=None,
        scene_count=None,
        source_mix=None,
        visual_style=None,
        tts_engine=None,
        metadata=None,
    ):
        data = self._load()

        entry = {
            "timestamp": datetime.now(
                timezone.utc
            ).isoformat(),

            "title": title,
            "topic": topic,

            "hook_pattern": hook_pattern,
            "hook_text": hook_text,

            "duration": duration,
            "scene_count": scene_count,

            "views": views,
            "avg_watch_time": avg_watch_time,
            "completion_rate": completion_rate,

            "likes": likes,
            "comments": comments,
            "shares": shares,
            "follows": follows,

            "source_mix": source_mix,
            "visual_style": visual_style,
            "tts_engine": tts_engine,

            "metadata": metadata or {},
        }

        # Calcul initial.
        entry = self._normalize_row(entry)

        data.append(entry)

        data = data[-self.MAX_HISTORY:]

        self._save(data)

        print(
            f"📊 Performance enregistrée : "
            f"{title}"
        )

        return entry

    # ------------------------------------------------------------
    # IMPORT DE STATISTIQUES EXTERNES
    # ------------------------------------------------------------

    def record_external_stats(
        self,
        video,
        topic=None,
        hook_pattern=None,
    ):
        """
        Permet d'enregistrer directement une vidéo provenant
        d'une API externe telle que Zernio.

        Les noms de champs courants sont automatiquement détectés.
        """

        def first_value(*keys):
            for key in keys:
                if key in video:
                    return video[key]
            return None

        title = first_value(
            "title",
            "name",
            "video_title",
        )

        views = first_value(
            "views",
            "view_count",
            "play_count",
        )

        likes = first_value(
            "likes",
            "like_count",
        )

        comments = first_value(
            "comments",
            "comment_count",
        )

        shares = first_value(
            "shares",
            "share_count",
        )

        follows = first_value(
            "follows",
            "followers_gained",
            "new_followers",
        )

        duration = first_value(
            "duration",
            "video_duration",
        )

        avg_watch_time = first_value(
            "avg_watch_time",
            "average_watch_time",
            "average_view_duration",
        )

        completion = first_value(
            "completion_rate",
            "completion",
            "watch_completion_rate",
        )

        return self.record(
            title=title or "unknown",
            topic=topic or first_value(
                "topic",
                "category",
            ),
            hook_pattern=(
                hook_pattern
                or first_value(
                    "hook_pattern"
                )
            ),
            duration=duration,
            views=views,
            avg_watch_time=avg_watch_time,
            completion_rate=completion,
            likes=likes,
            comments=comments,
            shares=shares,
            follows=follows,
            metadata={
                "external_source": "zernio",
                "external_id": first_value(
                    "id",
                    "video_id",
                ),
            },
        )

    # ------------------------------------------------------------
    # ANALYSE GÉNÉRALE
    # ------------------------------------------------------------

    def analyze(self):
        data = self._load()

        if not data:
            return {}

        normalized = [
            self._normalize_row(row)
            for row in data
        ]

        return {
            "videos": len(normalized),

            "avg_views": round(
                self._mean(
                    x.get("views")
                    for x in normalized
                ),
                2,
            ),

            "median_views": round(
                self._median(
                    x.get("views")
                    for x in normalized
                ),
                2,
            ),

            "avg_completion": round(
                self._mean(
                    x.get(
                        "completion_rate_normalized"
                    )
                    for x in normalized
                ) * 100,
                2,
            ),

            "avg_watch_time": round(
                self._mean(
                    x.get("avg_watch_time")
                    for x in normalized
                ),
                2,
            ),

            "avg_like_rate": round(
                self._mean(
                    x.get("like_rate")
                    for x in normalized
                ) * 100,
                3,
            ),

            "avg_comment_rate": round(
                self._mean(
                    x.get("comment_rate")
                    for x in normalized
                ) * 100,
                3,
            ),

            "avg_share_rate": round(
                self._mean(
                    x.get("share_rate")
                    for x in normalized
                ) * 100,
                3,
            ),

            "avg_follow_rate": round(
                self._mean(
                    x.get("follow_rate")
                    for x in normalized
                ) * 100,
                3,
            ),

            "best_video": self._get_best_video(
                normalized
            ),
        }

    # ------------------------------------------------------------
    # GROUPES
    # ------------------------------------------------------------

    def _group_by(self, field):
        data = self._load()

        groups = {}

        for row in data:
            value = row.get(field)

            if value is None:
                value = "unknown"

            value = str(value).strip()

            if not value:
                value = "unknown"

            groups.setdefault(
                value,
                [],
            ).append(row)

        return groups

    def _analyze_group(
        self,
        rows,
        group_name,
    ):
        normalized = [
            self._normalize_row(row)
            for row in rows
        ]

        scores = [
            self._compute_video_score(
                row,
                dataset=self._load(),
            )
            for row in normalized
        ]

        views = [
            row.get("views")
            for row in normalized
        ]

        completion = [
            row.get(
                "completion_rate_normalized"
            )
            for row in normalized
        ]

        watch = [
            row.get("avg_watch_time")
            for row in normalized
        ]

        shares = [
            row.get("shares")
            for row in normalized
        ]

        share_rates = [
            row.get("share_rate")
            for row in normalized
        ]

        return {
            "name": group_name,
            "videos": len(rows),

            "avg_score": round(
                self._mean(scores),
                2,
            ),

            "avg_views": round(
                self._mean(views),
                2,
            ),

            "median_views": round(
                self._median(views),
                2,
            ),

            "avg_completion": round(
                self._mean(completion) * 100,
                2,
            ),

            "avg_watch_time": round(
                self._mean(watch),
                2,
            ),

            "avg_shares": round(
                self._mean(shares),
                2,
            ),

            "avg_share_rate": round(
                self._mean(share_rates) * 100,
                3,
            ),
        }

    # ------------------------------------------------------------
    # HOOKS
    # ------------------------------------------------------------

    def analyze_hooks(self):
        groups = self._group_by(
            "hook_pattern"
        )

        result = []

        for pattern, rows in groups.items():

            if pattern == "unknown":
                continue

            stats = self._analyze_group(
                rows,
                pattern,
            )

            # Fiabilité statistique.
            confidence = min(
                len(rows) / 10,
                1.0,
            )

            # On évite qu'un pattern ayant
            # une seule vidéo prenne immédiatement
            # la première place.
            adjusted_score = (
                stats["avg_score"]
                * (
                    0.65
                    + 0.35 * confidence
                )
            )

            stats["confidence"] = round(
                confidence,
                2,
            )

            stats["adjusted_score"] = round(
                adjusted_score,
                2,
            )

            result.append(stats)

        result.sort(
            key=lambda x: (
                x["adjusted_score"],
                x["avg_views"],
            ),
            reverse=True,
        )

        return result

    # ------------------------------------------------------------
    # SUJETS
    # ------------------------------------------------------------

    def analyze_topics(self):
        groups = self._group_by(
            "topic"
        )

        result = []

        for topic, rows in groups.items():

            if topic == "unknown":
                continue

            stats = self._analyze_group(
                rows,
                topic,
            )

            result.append(stats)

        result.sort(
            key=lambda x: (
                x["avg_score"],
                x["avg_views"],
            ),
            reverse=True,
        )

        return result

    # ------------------------------------------------------------
    # DURÉES
    # ------------------------------------------------------------

    def analyze_durations(self):
        data = self._load()

        buckets = {
            "0-20s": [],
            "21-30s": [],
            "31-45s": [],
            "46-60s": [],
            "61s+": [],
        }

        for row in data:
            duration = self._safe_float(
                row.get("duration")
            )

            if duration is None:
                continue

            if duration <= 20:
                bucket = "0-20s"

            elif duration <= 30:
                bucket = "21-30s"

            elif duration <= 45:
                bucket = "31-45s"

            elif duration <= 60:
                bucket = "46-60s"

            else:
                bucket = "61s+"

            buckets[bucket].append(row)

        result = []

        for bucket, rows in buckets.items():

            if not rows:
                continue

            stats = self._analyze_group(
                rows,
                bucket,
            )

            result.append(stats)

        result.sort(
            key=lambda x: x["avg_score"],
            reverse=True,
        )

        return result

    # ------------------------------------------------------------
    # MEILLEURE VIDÉO
    # ------------------------------------------------------------

    def _get_best_video(self, data=None):
        if data is None:
            data = self._load()

        if not data:
            return None

        scored = []

        for row in data:
            score = self._compute_video_score(
                row,
                dataset=data,
            )

            scored.append(
                (
                    score,
                    row,
                )
            )

        scored.sort(
            key=lambda x: x[0],
            reverse=True,
        )

        score, video = scored[0]

        return {
            "score": score,
            "title": video.get(
                "title"
            ),
            "topic": video.get(
                "topic"
            ),
            "hook_pattern": video.get(
                "hook_pattern"
            ),
            "views": video.get(
                "views"
            ),
        }

    # ------------------------------------------------------------
    # VIDÉOS EXCEPTIONNELLES
    # ------------------------------------------------------------

    def get_breakout_videos(
        self,
        multiplier=2.0,
    ):
        """
        Détecte les vidéos dont les vues dépassent
        largement la médiane historique.
        """

        data = self._load()

        if len(data) < 3:
            return []

        views = [
            self._safe_float(
                row.get("views")
            )
            for row in data
        ]

        views = [
            value
            for value in views
            if value is not None
        ]

        if not views:
            return []

        median = statistics.median(
            views
        )

        if median <= 0:
            return []

        result = []

        for row in data:
            row_views = self._safe_float(
                row.get("views")
            )

            if (
                row_views is not None
                and row_views >= median * multiplier
            ):
                result.append({
                    "title": row.get(
                        "title"
                    ),
                    "topic": row.get(
                        "topic"
                    ),
                    "hook_pattern": row.get(
                        "hook_pattern"
                    ),
                    "views": row_views,
                    "multiple_of_median": round(
                        row_views / median,
                        2,
                    ),
                })

        result.sort(
            key=lambda x: x["views"],
            reverse=True,
        )

        return result

    # ------------------------------------------------------------
    # PATTERNS GAGNANTS
    # ------------------------------------------------------------

    def get_best_patterns(
        self,
        min_samples=None,
    ):
        if min_samples is None:
            min_samples = (
                self.MIN_PATTERN_SAMPLES
            )

        analysis = self.analyze_hooks()

        valid = [
            item
            for item in analysis
            if item["videos"] >= min_samples
        ]

        valid.sort(
            key=lambda x: (
                x["adjusted_score"],
                x["avg_views"],
            ),
            reverse=True,
        )

        return [
            item["name"]
            for item in valid
        ]

    # ------------------------------------------------------------
    # RECOMMANDATIONS
    # ------------------------------------------------------------

    def generate_recommendations(self):
        """
        Génère des recommandations directement utilisables
        par ContentBrain.
        """

        data = self._load()

        if len(data) < 3:
            return {
                "status": "insufficient_data",
                "message": (
                    "Pas encore assez de vidéos "
                    "pour tirer des conclusions fiables."
                ),
                "recommended_hooks": [],
                "recommended_topics": [],
                "recommended_duration": None,
                "warnings": [],
            }

        analysis = self.analyze()

        hooks = self.analyze_hooks()
        topics = self.analyze_topics()
        durations = self.analyze_durations()

        recommended_hooks = [
            item["name"]
            for item in hooks
            if item["videos"]
            >= self.MIN_PATTERN_SAMPLES
        ][:3]

        recommended_topics = [
            item["name"]
            for item in topics
            if item["videos"]
            >= self.MIN_PATTERN_SAMPLES
        ][:5]

        recommended_duration = None

        if durations:
            best_duration = durations[0]

            if best_duration["videos"] >= 2:
                recommended_duration = (
                    best_duration["name"]
                )

        breakout = self.get_breakout_videos()

        warnings = []

        if analysis["avg_completion"] < 50:
            warnings.append(
                "Rétention moyenne faible : "
                "renforcer le hook et réduire les longueurs."
            )

        if analysis["avg_share_rate"] < 0.5:
            warnings.append(
                "Taux de partage faible : "
                "renforcer les révélations, surprises "
                "et informations partageables."
            )

        if not recommended_hooks:
            warnings.append(
                "Pas encore assez de données "
                "pour privilégier un pattern de hook."
            )

        return {
            "status": "ok",

            "recommended_hooks":
                recommended_hooks,

            "recommended_topics":
                recommended_topics,

            "recommended_duration":
                recommended_duration,

            "best_video":
                analysis.get(
                    "best_video"
                ),

            "breakout_videos":
                breakout[:5],

            "warnings":
                warnings,

            "global_metrics": analysis,
        }

    # ------------------------------------------------------------
    # PROMPT POUR CONTENT BRAIN
    # ------------------------------------------------------------

    def build_brain_context(self):
        """
        Produit un bloc textuel court que ContentBrain peut
        injecter dans son prompt de génération.

        Exemple :

            PERFORMANCE LEARNING:
            Hooks performants : curiosity_gap, shocking_fact
            Sujets performants : ...
            Durée dominante : 31-45s
        """

        recommendations = (
            self.generate_recommendations()
        )

        if (
            recommendations.get("status")
            != "ok"
        ):
            return ""

        lines = [
            "PERFORMANCE LEARNING",
            "====================",
        ]

        hooks = recommendations.get(
            "recommended_hooks",
            [],
        )

        topics = recommendations.get(
            "recommended_topics",
            [],
        )

        duration = recommendations.get(
            "recommended_duration"
        )

        if hooks:
            lines.append(
                "Hooks performants : "
                + ", ".join(hooks)
            )

        if topics:
            lines.append(
                "Sujets/angles performants : "
                + ", ".join(topics)
            )

        if duration:
            lines.append(
                "Plage de durée performante : "
                + duration
            )

        breakout = recommendations.get(
            "breakout_videos",
            [],
        )

        if breakout:
            best = breakout[0]

            lines.append(
                "Dernier breakout : "
                + f"{best.get('title')} "
                + f"({best.get('views')} vues)"
            )

            if best.get(
                "hook_pattern"
            ):
                lines.append(
                    "Pattern du breakout : "
                    + str(
                        best.get(
                            "hook_pattern"
                        )
                    )
                )

        warnings = recommendations.get(
            "warnings",
            [],
        )

        for warning in warnings[:3]:
            lines.append(
                "Attention : "
                + warning
            )

        lines.append(
            "Ne pas copier mécaniquement un ancien "
            "contenu : utiliser ces données comme "
            "signaux de probabilité."
        )

        return "\n".join(lines)

    # ------------------------------------------------------------
    # RAPPORT COMPLET
    # ------------------------------------------------------------

    def get_full_report(self):
        return {
            "generated_at": datetime.now(
                timezone.utc
            ).isoformat(),

            "global": self.analyze(),

            "hooks":
                self.analyze_hooks(),

            "topics":
                self.analyze_topics(),

            "durations":
                self.analyze_durations(),

            "breakouts":
                self.get_breakout_videos(),

            "recommendations":
                self.generate_recommendations(),
        }

    def print_report(self):
        report = self.get_full_report()

        print("\n")
        print("=" * 60)
        print("📊 PERFORMANCE BRAIN")
        print("=" * 60)

        global_stats = report.get(
            "global",
            {},
        )

        print(
            f"Vidéos analysées : "
            f"{global_stats.get('videos', 0)}"
        )

        print(
            f"Vues moyennes : "
            f"{global_stats.get('avg_views', 0)}"
        )

        print(
            f"Vues médianes : "
            f"{global_stats.get('median_views', 0)}"
        )

        print(
            f"Rétention moyenne : "
            f"{global_stats.get('avg_completion', 0)}%"
        )

        print(
            f"Watch time moyen : "
            f"{global_stats.get('avg_watch_time', 0)}s"
        )

        print(
            f"Taux de partage : "
            f"{global_stats.get('avg_share_rate', 0)}%"
        )

        print("\n🏆 HOOKS")

        for hook in report.get(
            "hooks",
            []
        )[:5]:

            print(
                f"  • {hook['name']} | "
                f"{hook['videos']} vidéos | "
                f"score={hook['adjusted_score']} | "
                f"vues={hook['avg_views']}"
            )

        print("\n🔥 TOP SUJETS")

        for topic in report.get(
            "topics",
            []
        )[:5]:

            print(
                f"  • {topic['name']} | "
                f"{topic['videos']} vidéos | "
                f"score={topic['avg_score']} | "
                f"vues={topic['avg_views']}"
            )

        print("\n🚀 BREAKOUTS")

        for video in report.get(
            "breakouts",
            []
        )[:5]:

            print(
                f"  • {video['title']} | "
                f"{video['views']} vues | "
                f"x{video['multiple_of_median']}"
            )

        print("\n🧠 RECOMMANDATIONS")

        recommendations = report.get(
            "recommendations",
            {},
        )

        for hook in recommendations.get(
            "recommended_hooks",
            [],
        ):
            print(
                f"  → Hook : {hook}"
            )

        for topic in recommendations.get(
            "recommended_topics",
            [],
        ):
            print(
                f"  → Angle : {topic}"
            )

        if recommendations.get(
            "recommended_duration"
        ):
            print(
                "  → Durée : "
                + recommendations[
                    "recommended_duration"
                ]
            )

        for warning in recommendations.get(
            "warnings",
            [],
        ):
            print(
                f"  ⚠️ {warning}"
            )

        print("=" * 60)
