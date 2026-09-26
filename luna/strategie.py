"""Strategie editoriale Luna : croissance, stories, reels et monetisation.

Les seuils de monetisation sont des reperes de suivi, pas des garanties
d'eligibilite ou de revenus. Verifier l'etat reel des programmes dans les
dashboards des plateformes.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, time, timedelta
import json
from pathlib import Path


@dataclass(frozen=True)
class Slot:
    heure: str
    content_format: str
    media_type: str
    platform: str
    monetization_track: str
    objectif: str
    duree: int = 10


PILIERS = (
    "lieux_instagrammables",
    "restaurants_bars_cafes",
    "vie_etudiante_finance",
    "mode_du_quotidien",
    "sorties_et_voyages",
    "coulisses_ia",
)

SEMAINE = {
    0: (
        Slot("08:15", "story", "photo", "instagram", "growth", "routine_matinale"),
        Slot("12:30", "feed_photo", "photo", "instagram", "growth", "lieu_ou_cafe"),
        Slot("18:30", "reel", "video", "instagram", "growth", "decouverte_lieu"),
        Slot("20:30", "tiktok_short", "video", "tiktok", "growth", "hook_sortie"),
        Slot("21:15", "tiktok_rewards", "video", "tiktok", "tiktok_creator_rewards",
             "format_original_60_plus", 75),
    ),
    1: (
        Slot("09:00", "story", "photo", "instagram", "growth", "etudiante"),
        Slot("13:00", "reel", "video", "instagram", "growth", "food"),
        Slot("19:00", "feed_photo", "photo", "instagram", "growth", "portrait_naturel"),
        Slot("20:45", "tiktok_short", "video", "tiktok", "growth", "tendance_adaptee"),
    ),
    2: (
        Slot("08:30", "story", "photo", "instagram", "growth", "question_abonnes"),
        Slot("12:45", "feed_photo", "photo", "instagram", "growth", "restaurant"),
        Slot("18:45", "reel", "video", "instagram", "growth", "avant_apres_lieu"),
        Slot("21:00", "tiktok_rewards", "video", "tiktok", "tiktok_creator_rewards",
             "guide_original_60_plus", 75),
    ),
    3: (
        Slot("09:00", "story", "photo", "instagram", "growth", "cafe_travail"),
        Slot("12:30", "reel", "video", "instagram", "growth", "look_de_la_journee"),
        Slot("19:15", "feed_photo", "photo", "instagram", "growth", "sortie"),
        Slot("20:30", "tiktok_short", "video", "tiktok", "growth", "micro_vlog"),
    ),
    4: (
        Slot("08:45", "story", "photo", "instagram", "growth", "teaser_weekend"),
        Slot("13:00", "feed_photo", "photo", "instagram", "growth", "bar_ou_restaurant"),
        Slot("18:30", "reel", "video", "instagram", "growth", "vlog_sortie"),
        Slot("20:45", "tiktok_short", "video", "tiktok", "growth", "sortie"),
        Slot("22:00", "tiktok_rewards", "video", "tiktok", "tiktok_creator_rewards",
             "storytelling_60_plus", 90),
    ),
    5: (
        Slot("10:00", "story", "photo", "instagram", "growth", "weekend"),
        Slot("14:00", "reel", "video", "instagram", "growth", "restaurant_bar"),
        Slot("18:00", "feed_photo", "photo", "instagram", "growth", "lieu_photo"),
        Slot("20:00", "tiktok_short", "video", "tiktok", "growth", "vlog"),
    ),
    6: (
        Slot("10:30", "story", "photo", "instagram", "growth", "recap_weekend"),
        Slot("13:30", "feed_photo", "photo", "instagram", "growth", "photo_spontanee"),
        Slot("18:30", "reel", "video", "instagram", "growth", "best_moment"),
        Slot("20:30", "tiktok_rewards", "video", "tiktok", "tiktok_creator_rewards",
             "recit_original_60_plus", 75),
    ),
}

HIGHLIGHTS = (
    "Metz", "Paris", "Restaurants", "Bars", "Cafes", "Voyages", "Looks", "Luna"
)

MONETISATION = {
    "instagram_gifts": {"repere_followers": 5000, "verification": "dashboard"},
    "instagram_subscriptions": {"verification": "dashboard"},
    "tiktok_creator_rewards": {
        "repere_followers": 10000, "repere_views_30d": 100000,
        "video_min_sec": 60, "compte": "personnel",
    },
    "tiktok_one": {
        "repere_followers": 10000, "repere_views_30d": 1000,
        "repere_posts_30d": 3,
    },
    "tiktok_series": {
        "repere_followers": 10000, "repere_views_30d": 1000,
        "repere_posts_30d": 3, "age_compte_jours": 30,
    },
    "brand_deals": {"verification": "media_kit + conformite + audience_engagee"},
}

BASE_PROMPTS = {
    "lieu_ou_cafe": "Discover a photogenic local place in an authentic phone photo. Show the environment first and Luna naturally in it.",
    "decouverte_lieu": "Create a short location-discovery video with a strong first-second hook and a natural human reaction.",
    "restaurant": "Show an atmospheric restaurant visit: venue identity, dish, Luna reaction, candid smartphone realism.",
    "bar_ou_restaurant": "Show a photogenic evening venue, food or drink, ambiance and Luna reacting naturally, never like an advertisement unless explicitly sponsored.",
    "restaurant_bar": "Create a lively evening discovery of a restaurant or bar, with a clear reason viewers would save the place.",
    "food": "Create a candid food mini-vlog focused on venue atmosphere, the dish and Luna's genuine reaction.",
    "portrait_naturel": "Create a natural everyday portrait with a real environment and visible phone-camera texture, never a studio shoot.",
    "sortie": "Create an authentic evening-out scene with handheld movement and a clear social hook.",
    "vlog_sortie": "Create a short outing vlog with a fast hook, place reveal and human reaction.",
    "format_original_60_plus": "Create an original 60-90 second narrated mini-vlog with a beginning, useful details, personal reaction and ending.",
    "guide_original_60_plus": "Create an original 60-90 second guide with route/context, practical details only when verified, and Luna's honest reaction.",
    "storytelling_60_plus": "Create an original 60-90 second story around a local outing with three concrete details and a satisfying ending.",
    "recit_original_60_plus": "Create an original 60-90 second recap with context, what surprised Luna, and one practical takeaway.",
    "question_abonnes": "Create a Story designed to trigger replies: one concrete question, natural environment, readable text area.",
    "routine_matinale": "Create a simple morning Story around coffee, study or getting ready, candid phone realism.",
    "teaser_weekend": "Create a Story teaser for an upcoming outing, with a visual clue and a question to the audience.",
}


def slots_du_jour(jour: datetime) -> list[Slot]:
    # Stories en plusieurs touches : matin, milieu de journee, soir + un
    # element destine a etre conserve dans un Highlight.
    slots = list(SEMAINE[jour.weekday()])
    slots.extend((
        Slot("16:00", "story", "photo", "instagram", "growth", "coulisses_sortie"),
        Slot("22:30", "story", "photo", "instagram", "growth", "reaction_soir"),
        Slot("23:00", "highlight_story", "photo", "instagram", "growth", "lieu_a_conserver"),
    ))
    return slots


def prochaine_date(moment: datetime, slot: Slot) -> datetime:
    hh, mm = (int(x) for x in slot.heure.split(":"))
    return datetime.combine(moment.date(), time(hh, mm), tzinfo=moment.tzinfo)


def construire_prompt(slot: Slot, lieu: str = "", ville: str = "") -> str:
    base = BASE_PROMPTS.get(
        slot.objectif,
        "Create original authentic social content with a strong opening, natural movement and a clear reason to comment or save.",
    )
    contexte = f" Location: {lieu}, {ville}." if lieu else ""
    return base + contexte


def plan_hebdo() -> list[dict]:
    out = []
    for jour in range(7):
        for slot in SEMAINE[jour]:
            out.append({"jour": jour, **asdict(slot)})
    return out


def strategie_resume() -> dict:
    return {
        "piliers": list(PILIERS),
        "highlights": list(HIGHLIGHTS),
        "monetisation": MONETISATION,
        "week": plan_hebdo(),
    }


def exporter(path: str = "data/luna_strategy.json") -> str:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(
            {"generated_at": datetime.now().isoformat(), **strategie_resume()},
            ensure_ascii=False, indent=2
        ),
        encoding="utf-8",
    )
    return str(p)
