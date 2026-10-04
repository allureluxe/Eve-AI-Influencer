"""Publie un Reel de @alluxe.ia AVEC une musique de la bibliothèque Instagram,
via bundle.social (offre gratuite : 20 publications par mois).

    python3 ops/alluxe_ia_bundle.py sons [recherche]          # sons tendance / recherche
    python3 ops/alluxe_ia_bundle.py reel 02-ia-invente-un-prix --son AUDIO_ID \
        --le 2026-10-05T19:00 [--essai] [--confirmer]
    python3 ops/alluxe_ia_bundle.py choisir 03-ia-invente   # 5 sons tendance adaptés au sujet
    python3 ops/alluxe_ia_bundle.py reel 03-ia-invente --son auto --le … # le meilleur des 5

LA MUSIQUE SUIT LE SUJET (4 oct., demande de l'opérateur : « musique
tendance jeune, tout style, adaptée au sujet »). Chaque ambiance a ses
styles qui tournent chez les jeunes ; on cherche ces styles dans la
bibliothèque Instagram et on garde en priorité ce qui est AUSSI dans les
tendances du moment, assez long pour couvrir le Reel.

Pourquoi un intermédiaire : Meta n'ouvre sa musique qu'à des partenaires
(testé le 4 oct. avec notre propre clé Facebook : aucun point d'accès).
bundle.social en est un. Le compte doit y être branché PAR FACEBOOK.
La musique d'Instagram ne marche que pour les Reels, jamais les Stories.

Sans --confirmer : affiche ce qui partirait, n'envoie rien.
--le : heure de Paris. --essai : « Reel d'essai », montré seulement à des
non-abonnés (Instagram le partage ensuite aux abonnés s'il marche).
Notre musique composée est coupée (volume 0) sous le son Instagram.
Un Reel programmé est noté dans data/alluxe_ia/publies.json (jamais deux fois).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from zoneinfo import ZoneInfo

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from alluxe_ia.reel import REELS  # noqa: E402  (légendes ; le 02 est rendu par reel_chat)

API = "https://api.bundle.social/api/v1/"
EQUIPE = "32828e26-6e40-4411-9361-13077da51aa7"   # « allureluxe's Org »
PUBLIES = os.path.join(RACINE, "data", "alluxe_ia", "publies.json")


def _cle() -> str:
    from gold_bot.env import charger_env
    charger_env()
    return os.environ["BUNDLE_SOCIAL_API_KEY"]


def _appel(methode: str, chemin: str, corps: bytes | None = None,
           type_contenu: str = "application/json") -> dict:
    entetes = {"x-api-key": _cle(), "user-agent": "alluxe-ia/1.0"}
    if corps is not None:
        entetes["content-type"] = type_contenu
    req = urllib.request.Request(API + chemin, data=corps, headers=entetes, method=methode)
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"bundle.social {e.code} sur {chemin} : {e.read().decode()[:400]}")


def sons(recherche: str = "") -> list[dict]:
    p = {"teamId": EQUIPE, "audioType": "music"}
    if recherche:
        p["searchQuery"] = recherche
    return _appel("GET", "misc/instagram/audio?" + urllib.parse.urlencode(p)).get("audio", [])


# Ambiance d'un sujet -> styles recherchés, du plus au moins prioritaire.
AMBIANCES: dict[str, list[str]] = {
    "mystere": ["phonk", "dark trap", "suspense", "slowed"],      # révélation, piège, « l'IA ment »
    "energie": ["funk brasileiro", "jersey club", "sped up", "hype"],  # listes rapides, astuces
    "punch": ["drill", "rap fr", "trap", "bass boosted"],         # « tu fais mal », méthode choc
    "motivation": ["afro", "afrobeats", "house", "motivation"],   # apprendre, progresser
    "chill": ["lofi", "chill", "r&b", "acoustic"],                # tuto posé, quotidien
}


def ambiance_du_reel(reel_id: str) -> str:
    return REELS[reel_id].get("ambiance", "energie")


def proposer_sons(reel_id: str, n: int = 5) -> list[dict]:
    """Les sons candidats, les mieux placés d'abord : style de l'ambiance
    ET présent dans les tendances, assez long pour tout le Reel."""
    duree_ms = int(sum(t.duree for t in REELS[reel_id]["temps"]) * 1000)
    tendance = {x["audio_id"] for x in sons()}
    vus, cand = set(), []
    for rang_style, style in enumerate(AMBIANCES[ambiance_du_reel(reel_id)]):
        for rang, x in enumerate(sons(style)):
            if x["audio_id"] in vus or int(x.get("duration_in_ms") or 0) < duree_ms:
                continue
            vus.add(x["audio_id"])
            x["_style"] = style
            x["_score"] = (0 if x["audio_id"] in tendance else 100) + rang_style * 10 + rang
            cand.append(x)
    return sorted(cand, key=lambda x: x["_score"])[:n]


def televerser(fichier: str) -> str:
    borne = uuid.uuid4().hex
    nom = os.path.basename(fichier)
    with open(fichier, "rb") as f:
        donnees = f.read()
    corps = (f"--{borne}\r\nContent-Disposition: form-data; name=\"teamId\"\r\n\r\n{EQUIPE}\r\n"
             f"--{borne}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{nom}\"\r\n"
             f"Content-Type: video/mp4\r\n\r\n").encode() + donnees + f"\r\n--{borne}--\r\n".encode()
    r = _appel("POST", "upload/", corps, f"multipart/form-data; boundary={borne}")
    return r["id"]


def corps_du_post(reel_id: str, upload_id: str, son: str, quand_utc: str, essai: bool) -> dict:
    ig = {
        "type": "REEL",
        "text": REELS[reel_id]["legende"],
        "uploadIds": [upload_id],
        "shareToFeed": True,
        "musicSoundInfo": {"musicSoundId": son, "musicSoundVolume": 100,
                           "videoOriginalSoundVolume": 0},
    }
    if essai:
        ig["trialParams"] = {"graduationStrategy": "SS_PERFORMANCE"}
    return {"teamId": EQUIPE, "title": f"alluxe.ia {reel_id}", "postDate": quand_utc,
            "status": "SCHEDULED", "socialAccountTypes": ["INSTAGRAM"], "data": {"INSTAGRAM": ig}}


def _heure_utc(le: str) -> str:
    local = dt.datetime.fromisoformat(le).replace(tzinfo=ZoneInfo("Europe/Paris"))
    if local < dt.datetime.now(ZoneInfo("Europe/Paris")) + dt.timedelta(minutes=5):
        raise SystemExit(f"--le {le} : l'heure doit être au moins 5 minutes dans le futur")
    return local.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def main() -> int:
    a = argparse.ArgumentParser()
    s = a.add_subparsers(dest="action", required=True)
    s1 = s.add_parser("sons")
    s1.add_argument("recherche", nargs="?", default="")
    s3 = s.add_parser("choisir")
    s3.add_argument("reel_id", choices=sorted(REELS))
    s2 = s.add_parser("reel")
    s2.add_argument("reel_id", choices=sorted(REELS))
    s2.add_argument("--son", required=True,
                    help="audio_id donné par « sons » ou « choisir », ou « auto »")
    s2.add_argument("--le", required=True, help="heure de Paris, ex. 2026-10-05T19:00")
    s2.add_argument("--essai", action="store_true")
    s2.add_argument("--confirmer", action="store_true")
    args = a.parse_args()

    if args.action == "sons":
        for x in sons(args.recherche)[:25]:
            print(f"{x['audio_id']:>20}  {x.get('display_artist', x.get('ig_username', '')):<25} "
                  f"{x.get('title', '')}  ({x.get('duration_in_ms', 0) // 1000} s)")
        return 0

    if args.action == "choisir":
        print(f"ambiance : {ambiance_du_reel(args.reel_id)}")
        for x in proposer_sons(args.reel_id):
            marque = "TENDANCE" if x["_score"] < 100 else "        "
            print(f"{x['audio_id']:>20}  {marque}  [{x['_style']}]  "
                  f"{x.get('display_artist', x.get('ig_username', ''))} - {x.get('title', '')}")
        return 0

    if args.son == "auto":
        choix = proposer_sons(args.reel_id, 1)
        if not choix:
            raise SystemExit("aucun son assez long trouvé pour cette ambiance")
        args.son = choix[0]["audio_id"]
        print(f"son choisi : {choix[0].get('title', '')} [{choix[0]['_style']}] -> {args.son}")

    cle = "reel:" + args.reel_id
    publies = json.load(open(PUBLIES)) if os.path.exists(PUBLIES) else {}
    if cle in publies:
        print(f"{args.reel_id} déjà programmé/publié le {publies[cle]['le']} : rien à faire")
        return 0
    quand = _heure_utc(args.le)
    fichier = os.path.join(RACINE, "data", "alluxe_ia", "reels", f"{args.reel_id}.mp4")
    if not os.path.exists(fichier):
        if args.reel_id == "02-ia-invente-un-prix":   # version « conversation animée »
            from alluxe_ia.reel_chat import rendre
        else:
            from alluxe_ia.reel import rendre
        rendre(args.reel_id)
    apercu = corps_du_post(args.reel_id, "<televersement>", args.son, quand, args.essai)
    print(json.dumps(apercu, ensure_ascii=False, indent=1))
    if not args.confirmer:
        print("\nESSAI À BLANC : rien n'est envoyé. Ajouter --confirmer pour programmer.")
        return 0
    upload = televerser(fichier)
    r = _appel("POST", "post/", json.dumps(corps_du_post(args.reel_id, upload, args.son, quand,
                                                           args.essai)).encode())
    publies[cle] = {"bundle_post_id": r.get("id"), "le": quand, "son": args.son}
    with open(PUBLIES, "w") as f:
        json.dump(publies, f, ensure_ascii=False, indent=2)
    print(f"PROGRAMMÉ : {args.reel_id} -> {r.get('id')} pour {args.le} (Paris)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
