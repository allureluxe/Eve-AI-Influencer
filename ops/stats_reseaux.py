#!/usr/bin/env python3
"""Statistiques alluxe.ia : Instagram, TikTok et YouTube, en un seul endroit.

    python3 ops/stats_reseaux.py              # rapport du jour, à l'écran
    python3 ops/stats_reseaux.py --telegram   # et l'envoie sur le téléphone

Les chiffres viennent de Windsor.ai, déjà relié aux trois comptes
(bundle.social ne donne pas les statistiques à notre abonnement : 403).
Il faut WINDSOR_API_KEY dans .env — onboard.windsor.ai, menu « API key ».

Chaque passage écrit un instantané daté dans data/alluxe_ia/stats/ :
l'historique se construit tout seul, jour après jour, et permet de
comparer une vidéo à la précédente au lieu de juger au ressenti.

Ce que le rapport met en avant, et pourquoi : la part de gens qui
décrochent dans les 3 premières secondes (Instagram) et la durée moyenne
regardée (TikTok). Tant que l'accroche ne retient pas, les abonnés ne
peuvent pas venir — ni le nombre de posts ni les hashtags n'y changent rien.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

API = "https://connectors.windsor.ai/"
DOSSIER = os.path.join(RACINE, "data", "alluxe_ia", "stats")
DEPUIS = "2026-10-01"   # ouverture d'alluxe.ia

CHAMPS = {
    "instagram": {
        "compte": ["followers_count", "media_count"],
        "posts": ["date", "media_type", "media_caption", "media_views", "media_reach",
                  "media_reel_avg_watch_time", "media_reel_skip_rate", "media_shares",
                  "media_saved", "media_like_count", "media_comments_count",
                  "media_permalink"],
    },
    "tiktok_organic": {
        "compte": ["total_followers_count", "videos_count"],
        "posts": ["date", "video_id", "video_caption", "video_views_count", "video_reach",
                  "video_average_time_watched", "video_full_watched_rate",
                  "video_duration", "video_likes", "video_shares", "video_new_followers"],
    },
    # Champs « Data API » (totaux à vie par vidéo) : les champs « Analytics »
    # (durée regardée, abonnés gagnés par vidéo) arrivent avec 2-3 jours de
    # retard chez YouTube et rendaient des lignes vides le 13 oct.
    "youtube": {
        "compte": ["channel_title", "subscriber_count", "video_count"],
        "posts": ["video_title", "published_at", "video_view_count", "video_like_count"],
    },
}
NOMS = {"instagram": "Instagram", "tiktok_organic": "TikTok", "youtube": "YouTube"}


def _cle() -> str:
    from gold_bot.env import charger_env
    charger_env()
    cle = os.environ.get("WINDSOR_API_KEY", "")
    if not cle:
        raise SystemExit("WINDSOR_API_KEY absente de .env (onboard.windsor.ai → API key).")
    return cle


def lire(connecteur: str, champs: list[str], date_from: str | None = None,
         date_to: str | None = None, preset: str | None = None) -> list[dict]:
    p = {"api_key": _cle(), "fields": ",".join(champs)}
    if preset:
        p["date_preset"] = preset
    else:
        p["date_from"], p["date_to"] = date_from, date_to
    url = API + connecteur + "?" + urllib.parse.urlencode(p)
    req = urllib.request.Request(url, headers={"user-agent": "alluxe-ia/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            corps = json.load(r)
    except urllib.error.HTTPError as e:
        # Jamais l'URL dans le message : elle porte la clé.
        raise RuntimeError(f"Windsor {e.code} sur {connecteur} : {e.read().decode()[:300]}")
    return corps.get("data", corps) if isinstance(corps, dict) else corps


def collecter() -> dict:
    aujourd_hui = date.today().isoformat()
    instantane = {"le": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    for connecteur, champs in CHAMPS.items():
        try:
            compte = lire(connecteur, champs["compte"], preset="last_1dT")
            posts = lire(connecteur, champs["posts"], DEPUIS, aujourd_hui)
            instantane[connecteur] = {"compte": compte[0] if compte else {}, "posts": posts}
        except Exception as e:
            instantane[connecteur] = {"erreur": str(e)[:300]}
    return instantane


def sauver(instantane: dict) -> str:
    os.makedirs(DOSSIER, exist_ok=True)
    chemin = os.path.join(DOSSIER, f"{date.today().isoformat()}.json")
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(instantane, f, ensure_ascii=False, indent=1)
    return chemin


def _veille(connecteur: str) -> dict:
    """L'instantané d'hier pour ce réseau, s'il existe (pour la progression)."""
    chemin = os.path.join(DOSSIER, f"{(date.today() - timedelta(days=1)).isoformat()}.json")
    try:
        with open(chemin, encoding="utf-8") as f:
            return json.load(f).get(connecteur, {})
    except (OSError, ValueError):
        return {}


def _titre(texte: str | None) -> str:
    t = (texte or "").split("\n")[0].strip()
    return t[:45] + ("…" if len(t) > 45 else "")


def _n(v) -> int:
    try:
        return int(float(v or 0))
    except (TypeError, ValueError):
        return 0


def rapport(inst: dict) -> str:
    lignes = [f"📊 alluxe.ia — {date.today().strftime('%d/%m')}"]

    ig = inst.get("instagram", {})
    if "erreur" in ig:
        lignes += ["", f"Instagram : indisponible ({ig['erreur'][:80]})"]
    else:
        abos = _n(ig["compte"].get("followers_count"))
        hier = _n(_veille("instagram").get("compte", {}).get("followers_count")) or abos
        reels = [p for p in ig["posts"] if p.get("media_type") == "REELS"]
        lignes += ["", f"📸 Instagram : {abos} abonnés ({abos - hier:+d} depuis hier)"]
        for p in sorted(reels, key=lambda p: p.get("date", ""))[-5:]:
            saut = p.get("media_reel_skip_rate")
            saut = f"{saut * 100:.0f} % partent avant 3 s" if saut is not None else "?"
            duree = (p.get("media_reel_avg_watch_time") or 0) / 1000
            lignes.append(f"• {p['date'][5:]} {_titre(p.get('media_caption'))}\n"
                          f"   {_n(p.get('media_views'))} vues · {duree:.1f} s regardées · {saut}")

    tt = inst.get("tiktok_organic", {})
    if "erreur" in tt:
        lignes += ["", f"TikTok : indisponible ({tt['erreur'][:80]})"]
    else:
        gagnes = sum(_n(p.get("video_new_followers")) for p in tt["posts"])
        lignes += ["", f"🎵 TikTok : {len(tt['posts'])} vidéos, {gagnes} abonnés gagnés au total"]
        for p in sorted(tt["posts"], key=lambda p: p.get("date", ""))[-5:]:
            vu = p.get("video_average_time_watched") or 0
            duree = p.get("video_duration") or 0
            lignes.append(f"• {p['date'][5:]} {_titre(p.get('video_caption'))}\n"
                          f"   {_n(p.get('video_views_count'))} vues · {vu:.1f} s sur {duree:.0f} s"
                          f" · +{_n(p.get('video_new_followers'))} abonnés")

    yt = inst.get("youtube", {})
    if "erreur" in yt:
        lignes += ["", "▶️ YouTube : pas encore relié à Windsor"]
    else:
        abos = _n(yt["compte"].get("subscriber_count"))
        lignes += ["", f"▶️ YouTube : {abos} abonnés"]
        hier = _n(_veille("youtube").get("compte", {}).get("subscriber_count")) or abos
        lignes[-1] += f" ({abos - hier:+d} depuis hier)"
        for p in sorted(yt["posts"], key=lambda p: p.get("published_at") or "")[-5:]:
            lignes.append(f"• {(p.get('published_at') or '')[5:10]} {_titre(p.get('video_title'))}\n"
                          f"   {_n(p.get('video_view_count'))} vues · {_n(p.get('video_like_count'))} j'aime")
    return "\n".join(lignes)


def envoyer_telegram(texte: str) -> None:
    from gold_bot.notifiers import http_json
    jeton, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not (jeton and chat):
        print("Telegram non configuré : rapport non envoyé.")
        return
    http_json(f"https://api.telegram.org/bot{jeton}/sendMessage", "POST",
              {"chat_id": chat, "text": texte, "disable_web_page_preview": True}, timeout=15)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--telegram", action="store_true", help="envoie le rapport sur Telegram")
    args = ap.parse_args()
    inst = collecter()
    chemin = sauver(inst)
    texte = rapport(inst)
    print(texte)
    print(f"\n(instantané : {os.path.relpath(chemin, RACINE)})")
    if args.telegram:
        envoyer_telegram(texte)
    return 0


if __name__ == "__main__":
    sys.exit(main())
