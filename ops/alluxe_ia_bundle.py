"""Publie un Reel de @alluxe.ia AVEC une musique de la bibliothèque Instagram,
via bundle.social (offre gratuite : 20 publications par mois).

    python3 ops/alluxe_ia_bundle.py sons [recherche]          # sons tendance / recherche
    python3 ops/alluxe_ia_bundle.py reel 02-ia-invente-un-prix --son AUDIO_ID \
        --le 2026-10-05T19:00 [--essai] [--confirmer]

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

from alluxe_ia.reel import REELS as _REELS_TEXTE  # noqa: E402  (le 02 est rendu par reel_chat)
from alluxe_ia.reel_photos import REELS as _REELS_PHOTOS  # noqa: E402
from alluxe_ia.reel_captures import REELS as _REELS_CAPTURES  # noqa: E402

REELS = {**_REELS_TEXTE, **_REELS_PHOTOS, **_REELS_CAPTURES}

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


SONS_TENDANCE_PREFERES = [
    ("Patient Zero", "Taylor Swift"),
    ("Nicole Kidman", "ADÉLA"),
    ("Funkytown", "Lipps Inc."),
    ("Upside Down", "Diana Ross"),
    ("Espresso", "Sabrina Carpenter"),
    ("God's Plan", "Drake"),
    ("MONACO", "Bad Bunny"),
    ("Sexy Nana", "Aya Nakamura"),
    ("Raindance", "Dave, Tems"),
    ("Jet Lag", "Tiakola, Jorja Smith"),
    ("La Nocturne", "Tiakola, Theodora"),
    ("STORM II", "GENER8ION, Yung Lean"),
    # 4 oct., choix de l'opérateur pour le Reel « 5 choses à ne jamais coller ».
    ("They Don't Care About Us (Remastered Version)", "Michael Jackson"),
    # 4 oct., l'opérateur : MJ ne collait pas, remplacé par LABOUR.
    ("LABOUR (the cacophony)", "Paris Paloma"),
    # 6 oct., choix de l'opérateur pour le Reel 04 « captures », calé sur le refrain.
    ("Unstoppable", "Sia"),
]


def sons(recherche: str = "") -> list[dict]:
    p = {"teamId": EQUIPE, "audioType": "music"}
    if recherche:
        p["searchQuery"] = recherche
    return _appel("GET", "misc/instagram/audio?" + urllib.parse.urlencode(p)).get("audio", [])


def son_connu(audio_id: str) -> dict:
    """Valide qu'un audio choisi correspond réellement à un titre/artiste connu."""
    tous = sons("")
    for x in tous:
        if str(x.get("audio_id")) == str(audio_id):
            titre = (x.get("title") or "").strip().lower()
            artiste = (x.get("display_artist") or x.get("ig_username") or "").strip().lower()
            for wanted_title, wanted_artist in SONS_TENDANCE_PREFERES:
                if titre == wanted_title.lower() and wanted_artist.lower() in artiste:
                    return x
            raise RuntimeError(
                f"Audio {audio_id} trouvé mais refusé : {x.get('title')} — {x.get('display_artist')}. "
                "ALLUXE n'accepte pas les sons génériques/inconnus."
            )
    raise RuntimeError(
        f"Audio {audio_id} introuvable dans la bibliothèque Instagram accessible. "
        "Publication bloquée plutôt que de choisir un morceau au hasard."
    )


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


def corps_du_post(reel_id: str, upload_id: str, son: str, quand_utc: str, essai: bool,
                  debut_ms: int | None = None, duree_ms: int | None = None) -> dict:
    ig = {
        "type": "REEL",
        "text": REELS[reel_id]["legende"],
        "uploadIds": [upload_id],
        "shareToFeed": True,
        "musicSoundInfo": {"musicSoundId": son, "musicSoundVolume": 100,
                           "videoOriginalSoundVolume": 0},
    }
    # Le passage du morceau (6 oct., l'opérateur : « pas le début des musiques,
    # un passage qui accroche ») : sans --debut, Instagram part du début.
    # ATTENTION, CONSTATÉ LE 6 OCT. : avec --debut 0:44.3 (Sia, Unstoppable) le Reel
    # est parti SANS AUCUNE MUSIQUE, sans erreur côté bundle.social (qui n'a pas
    # gardé musicSoundStart/End). Cause non tranchée : ces champs, ou un titre
    # refusé aux comptes pro. Ne pas réutiliser --debut sans un essai (--essai).
    if debut_ms is not None:
        ig["musicSoundInfo"]["musicSoundStart"] = debut_ms
        if duree_ms:
            ig["musicSoundInfo"]["musicSoundEnd"] = debut_ms + duree_ms
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
    s1.add_argument("--connus", action="store_true", help="exclut instrumentaux et sons génériques")
    s2 = s.add_parser("reel")
    s2.add_argument("reel_id", choices=sorted(REELS))
    s2.add_argument("--son", required=True, help="audio_id donné par « sons »")
    s2.add_argument("--le", required=True, help="heure de Paris, ex. 2026-10-05T19:00")
    s2.add_argument("--essai", action="store_true")
    s2.add_argument("--debut", help="début du passage dans le morceau, ex. 0:44.3 (le refrain, pas l'intro)")
    s2.add_argument("--confirmer", action="store_true")
    args = a.parse_args()

    if args.action == "sons":
        resultats = sons(args.recherche)
        if args.connus:
            termes_interdits = ("instrumental", "piano", "lofi", "ambient", "background", "sound effect", "original audio")
            resultats = [x for x in resultats if not any(t in (x.get("title", "").lower()) for t in termes_interdits)]
        for x in resultats[:25]:
            print(f"{x['audio_id']:>20}  {x.get('display_artist', x.get('ig_username', '')):<25} "
                  f"{x.get('title', '')}  ({x.get('duration_in_ms', 0) // 1000} s)")
        return 0

    cle = "reel:" + args.reel_id
    publies = json.load(open(PUBLIES)) if os.path.exists(PUBLIES) else {}
    if cle in publies:
        print(f"{args.reel_id} déjà programmé/publié le {publies[cle]['le']} : rien à faire")
        return 0
    quand = _heure_utc(args.le)
    # Garde-fou : le morceau doit être un vrai titre connu de notre liste,
    # jamais un son obscur renvoyé par le catalogue par défaut.
    audio = son_connu(args.son)
    print(f"SON VALIDÉ : {audio.get('title')} — {audio.get('display_artist')} ({audio.get('audio_id')})")
    fichier = os.path.join(RACINE, "data", "alluxe_ia", "reels", f"{args.reel_id}.mp4")
    if not os.path.exists(fichier):
        if args.reel_id in _REELS_CAPTURES:
            from alluxe_ia.reel_captures import rendre
        elif args.reel_id in _REELS_PHOTOS:
            from alluxe_ia.reel_photos import rendre
        elif args.reel_id == "02-ia-invente-un-prix":   # version « conversation animée »
            from alluxe_ia.reel_chat import rendre
        else:
            from alluxe_ia.reel import rendre
        rendre(args.reel_id)
    debut_ms = duree_ms = None
    if args.debut:
        m, s = (args.debut.split(":") + ["0"])[:2] if ":" in args.debut else ("0", args.debut)
        debut_ms = int((int(m) * 60 + float(s)) * 1000)
        try:
            import re
            import subprocess
            sortie = subprocess.run(["ffmpeg", "-i", fichier], capture_output=True, text=True).stderr
            h, mi, se = re.search(r"Duration: (\d+):(\d+):([\d.]+)", sortie).groups()
            duree_ms = int((int(h) * 3600 + int(mi) * 60 + float(se)) * 1000)
        except Exception:  # noqa: BLE001 -- sans durée, Instagram coupe à la fin de la vidéo
            duree_ms = None
    apercu = corps_du_post(args.reel_id, "<televersement>", args.son, quand, args.essai, debut_ms, duree_ms)
    print(json.dumps(apercu, ensure_ascii=False, indent=1))
    if not args.confirmer:
        print("\nESSAI À BLANC : rien n'est envoyé. Ajouter --confirmer pour programmer.")
        return 0
    upload = televerser(fichier)
    r = _appel("POST", "post/", json.dumps(corps_du_post(args.reel_id, upload, args.son, quand,
                                                           args.essai, debut_ms, duree_ms)).encode())
    publies[cle] = {"bundle_post_id": r.get("id"), "le": quand, "son": args.son, "debut_ms": debut_ms}
    with open(PUBLIES, "w") as f:
        json.dump(publies, f, ensure_ascii=False, indent=2)
    print(f"PROGRAMMÉ : {args.reel_id} -> {r.get('id')} pour {args.le} (Paris)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
