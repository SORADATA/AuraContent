"""
modules/visuals/scene_map_hologram.py

Generateur generique de "cartes hologrammes" animees (style wireframe neon)
pour illustrer n'importe quel sujet geolocalise : stations fantomes,
monuments disparus, lieux de faits historiques, itineraires, etc.

Concu pour etre appele depuis brain.py / composer.py comme les autres
generateurs visuels du repo (ex: wan_video_generator.py), avec une
interface simple : on donne une VILLE + une liste de POINTS D'INTERET,
le module retourne le chemin d'un fichier video pret a etre compose.

Aucune dependance payante : OSMnx (OpenStreetMap) + Manim (rendu) + FFmpeg.
"""

from __future__ import annotations

import os
import hashlib
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

CACHE_DIR = os.path.join("assets", "cache", "hologram_maps")
os.makedirs(CACHE_DIR, exist_ok=True)


@dataclass
class HologramPOI:
    """Un point d'interet a faire pulser sur la carte (generique : station,
    monument, lieu d'evenement, etc.)."""
    name: str
    lat: Optional[float] = None
    lon: Optional[float] = None
    color: str = "#ff3b3b"          # rouge neon par defaut
    label_position: str = "auto"    # "auto" | "top" | "bottom" | "left" | "right"


@dataclass
class HologramMapConfig:
    """Configuration generique d'une scene carte-hologramme.

    city: n'importe quelle ville/lieu geocodable par OSMnx/Nominatim
          (ex: "Paris, France", "Tokyo, Japan", "New York, USA").
    network_type: "drive" | "walk" | "bike" | "all" - type de reseau
          OSM a afficher en fond (rues, metro approxime via "walk"/"all").
    theme: permet de changer la palette sans dupliquer le code
          (ex: "cyan_noir", "ambre_noir", "violet_noir").
    """
    city: str
    pois: List[HologramPOI] = field(default_factory=list)
    network_type: str = "drive"
    theme: str = "cyan_noir"
    duration_per_poi: float = 2.5
    resolution: Tuple[int, int] = (1080, 1920)  # vertical par defaut (Shorts/TikTok)
    fps: int = 30
    zoom_on_poi: bool = True
    output_name: Optional[str] = None


THEMES = {
    "cyan_noir":   {"bg": "#000000", "edge": "#00eaff", "glow": "#00eaff", "label": "#e6faff"},
    "ambre_noir":  {"bg": "#000000", "edge": "#ffb347", "glow": "#ffb347", "label": "#fff2df"},
    "violet_noir": {"bg": "#000000", "edge": "#b967ff", "glow": "#b967ff", "label": "#f1e6ff"},
    "vert_matrix": {"bg": "#000000", "edge": "#39ff14", "glow": "#39ff14", "label": "#e8ffe0"},
}


def _cache_key(config: HologramMapConfig) -> str:
    raw = "{}|{}|{}|".format(config.city, config.network_type, config.theme)
    raw += "|".join("{}:{}:{}".format(p.name, p.lat, p.lon) for p in config.pois)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _geocode_pois(config: HologramMapConfig) -> None:
    """Complete lat/lon manquants via geocodage (Nominatim / OSMnx),
    pour que l'appelant puisse ne fournir que des noms de lieux."""
    import osmnx as ox

    for poi in config.pois:
        if poi.lat is not None and poi.lon is not None:
            continue
        query = "{}, {}".format(poi.name, config.city)
        try:
            lat, lon = ox.geocode(query)
            poi.lat, poi.lon = lat, lon
            logger.info("Geocodage OK: %s -> (%.5f, %.5f)", query, lat, lon)
        except Exception as exc:
            logger.warning("Geocodage echoue pour '%s' (%s). POI ignore.", query, exc)


def fetch_city_network(config: HologramMapConfig):
    """Telecharge le graphe de rues/reseau reel de la ville via OSMnx.
    Retourne un graphe networkx utilisable pour le rendu."""
    import osmnx as ox

    logger.info("Telechargement du reseau OSM pour '%s' (%s)...", config.city, config.network_type)
    graph = ox.graph_from_place(config.city, network_type=config.network_type, simplify=True)
    return graph


def render_hologram_map_video(config: HologramMapConfig) -> str:
    """Point d'entree principal du module.

    Genere une video MP4 de carte "hologramme" pour n'importe quelle ville
    et n'importe quelle liste de points d'interet, puis retourne le chemin
    du fichier genere (a consommer par composer.py / composer_finance.py).

    Ne leve pas d'exception bloquante sur un POI mal geocode : il est
    simplement ignore (log warning) pour ne pas casser tout le run batch.
    """
    if not config.pois:
        raise ValueError("HologramMapConfig.pois ne doit pas etre vide.")

    theme = THEMES.get(config.theme, THEMES["cyan_noir"])
    _geocode_pois(config)

    valid_pois = [p for p in config.pois if p.lat is not None and p.lon is not None]
    if not valid_pois:
        raise RuntimeError("Aucun POI geocode avec succes pour la ville '{}'.".format(config.city))

    output_name = config.output_name or "hologram_{}.mp4".format(_cache_key(config))
    output_path = os.path.join(CACHE_DIR, output_name)

    if os.path.exists(output_path):
        logger.info("Cache hit: %s deja genere, reutilisation.", output_path)
        return output_path

    graph = fetch_city_network(config)
    _render_with_manim(graph, valid_pois, theme, config, output_path)

    return output_path


def _render_with_manim(graph, pois: List[HologramPOI], theme: dict,
                        config: HologramMapConfig, output_path: str) -> None:
    """Rendu de la scene avec Manim : reseau en wireframe + POIs pulsants.

    Genere un script Manim temporaire et l'execute en subprocess pour
    rester decouple du reste du pipeline (pas d'import lourd de manim
    au niveau module, seulement a l'appel)."""
    import subprocess
    import tempfile
    import shutil

    nodes = list(graph.nodes(data=True))
    edges = list(graph.edges())
    xs = [d["x"] for _, d in nodes]
    ys = [d["y"] for _, d in nodes]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    def normalize(x, y):
        nx_ = (x - min_x) / (max_x - min_x + 1e-9) * 14 - 7
        ny_ = (y - min_y) / (max_y - min_y + 1e-9) * 14 - 7
        return nx_, ny_

    edge_lines = []
    node_lookup = {n: d for n, d in nodes}
    for u, v in edges:
        if u in node_lookup and v in node_lookup:
            x1, y1 = normalize(node_lookup[u]["x"], node_lookup[u]["y"])
            x2, y2 = normalize(node_lookup[v]["x"], node_lookup[v]["y"])
            edge_lines.append((x1, y1, x2, y2))

    poi_points = []
    for poi in pois:
        px, py = normalize(poi.lon, poi.lat)
        poi_points.append((poi.name, px, py, poi.color))

    scene_code = _build_manim_scene_code(edge_lines, poi_points, theme, config)

    with tempfile.TemporaryDirectory() as tmp_dir:
        scene_file = os.path.join(tmp_dir, "hologram_scene.py")
        with open(scene_file, "w", encoding="utf-8") as f:
            f.write(scene_code)

        cmd = [
            "manim", "render", "-q", "h",
            "--fps", str(config.fps),
            "-r", "{},{}".format(config.resolution[0], config.resolution[1]),
            scene_file, "HologramMapScene",
        ]
        logger.info("Rendu Manim: %s", " ".join(cmd))
        result = subprocess.run(cmd, cwd=tmp_dir, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error("Manim stderr: %s", result.stderr[-2000:])
            raise RuntimeError("Echec du rendu Manim pour la carte hologramme.")

        rendered = _find_rendered_mp4(tmp_dir)
        if not rendered:
            raise RuntimeError("Fichier video Manim introuvable apres rendu.")
        shutil.copy(rendered, output_path)


def _find_rendered_mp4(tmp_dir: str) -> Optional[str]:
    for root, _, files in os.walk(tmp_dir):
        for f in files:
            if f.endswith(".mp4"):
                return os.path.join(root, f)
    return None


_MANIM_TEMPLATE = """
from manim import *

class HologramMapScene(Scene):
    def construct(self):
        self.camera.background_color = "{bg_color}"

        edges = {edges_repr}
        pois = {pois_repr}

        network = VGroup()
        for (x1, y1, x2, y2) in edges:
            line = Line([x1, y1, 0], [x2, y2, 0],
                        stroke_color="{edge_color}",
                        stroke_width=1, stroke_opacity=0.55)
            network.add(line)

        self.play(LaggedStart(*[Create(l) for l in network], lag_ratio=0.002), run_time=3)

        for name, px, py, color in pois:
            dot = Dot(point=[px, py, 0], color=color, radius=0.08)
            pulse = Circle(radius=0.08, color=color, stroke_width=3).move_to(dot.get_center())
            label = Text(name, font_size=22, color="{label_color}").next_to(dot, UP, buff=0.25)

            self.play(FadeIn(dot, scale=0.5), FadeIn(label, shift=UP*0.2), run_time=0.4)
            self.play(
                pulse.animate.scale(4).set_stroke(opacity=0),
                run_time=1.2,
                rate_func=linear,
            )
            self.wait({duration})
            self.play(FadeOut(label), run_time=0.3)

        self.wait(0.5)
"""


def _build_manim_scene_code(edge_lines, poi_points, theme: dict, config: HologramMapConfig) -> str:
    """Genere dynamiquement le code Manim de la scene (approche codegen,
    plus simple a maintenir que du bytecode/AST pour ce cas d'usage)."""
    return _MANIM_TEMPLATE.format(
        bg_color=theme["bg"],
        edge_color=theme["edge"],
        label_color=theme["label"],
        edges_repr=repr(edge_lines),
        pois_repr=repr(poi_points),
        duration=config.duration_per_poi,
    )


# ---------------------------------------------------------------------------
# Exemple d'utilisation generique (n'importe quelle ville / theme)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Exemple 1 : stations fantomes de Paris (le cas d'origine, mais
    # traite comme un cas parmi d'autres, pas un cas special en dur)
    demo_paris = HologramMapConfig(
        city="Paris, France",
        network_type="walk",
        theme="cyan_noir",
        pois=[
            HologramPOI(name="Croix-Rouge"),
            HologramPOI(name="Arsenal"),
            HologramPOI(name="Champ-de-Mars"),
            HologramPOI(name="Martin Nadaud"),
        ],
    )

    # Exemple 2 : un tout autre sujet, une tout autre ville, pour
    # prouver que rien n'est code en dur pour Paris/metro.
    demo_tokyo = HologramMapConfig(
        city="Tokyo, Japan",
        network_type="drive",
        theme="violet_noir",
        pois=[
            HologramPOI(name="Shibuya Crossing"),
            HologramPOI(name="Tokyo Tower"),
        ],
    )

    # render_hologram_map_video(demo_paris)
    # render_hologram_map_video(demo_tokyo)
