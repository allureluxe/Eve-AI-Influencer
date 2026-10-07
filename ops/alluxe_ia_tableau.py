"""Alimente l'onglet « alluxe.ia » de l'appli Alluxe Bot (7 oct. 2026).

    python3 ops/alluxe_ia_tableau.py stats              # compte + posts/Reels -> Supabase (cron 30 min)
    python3 ops/alluxe_ia_tableau.py cibles [--essai]   # la liste du jour « à commenter » (cron 8 h)
    python3 ops/alluxe_ia_tableau.py a-publier ID FICHIER.mp4 --titre T --legende-fichier L.txt
                                     [--reseau tiktok] [--musique "conseil"]

L'ASSISTANT COMMENTAIRES NE COMMENTE RIEN LUI-MÊME, et c'est délibéré : commenter,
liker ou s'abonner par un robot est du « comportement non authentique » pour
Instagram (actions bloquées, compte retiré des recommandations, voire supprimé).
Il TROUVE les posts récents et populaires des comptes IA francophones (recherche
officielle par hashtag) et PROPOSE un commentaire ; l'opérateur publie lui-même.
L'API officielle ne permet d'ailleurs ni de commenter chez les autres, ni de liker,
ni de s'abonner.

Limite Instagram : 30 hashtags différents par 7 jours -- la liste HASHTAGS en
garde 7, consultés chaque jour.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

IG = "17841461765610508"
GRAPH = "https://graph.facebook.com/v21.0"
HASHTAGS = ["intelligenceartificielle", "chatgpt", "iagenerative", "outilsia",
            "automatisation", "nocode", "claudeai"]
NB_CIBLES = 10
MODELE = os.getenv("ALLUXE_IA_MODELE", "claude-sonnet-5-5")
MOTS_FR = {"le", "la", "les", "des", "une", "est", "pour", "avec", "pas", "sur", "dans",
           "que", "qui", "tu", "vous", "ton", "votre", "mais", "plus", "comment", "c'est"}


def _env() -> None:
    from gold_bot.env import charger_env
    charger_env()


def graph(chemin: str, **p) -> dict:
    p["access_token"] = os.environ["INSTAGRAM_FB_TOKEN"]
    url = f"{GRAPH}/{chemin}?" + urllib.parse.urlencode(p)
    for essai in range(3):                  # la recherche par hashtag est parfois très lente
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            return {"err": e.read().decode()[:300]}
        except (TimeoutError, OSError):
            continue
    return {"err": "délai dépassé"}


def supabase(methode: str, table: str, corps=None, requete: str = "", prefer: str = "") -> list | dict:
    url = os.environ["SUPABASE_URL"].rstrip("/") + f"/rest/v1/{table}{requete}"
    cle = os.environ["SUPABASE_SERVICE_KEY"]
    entetes = {"apikey": cle, "authorization": f"Bearer {cle}", "content-type": "application/json"}
    if prefer:
        entetes["prefer"] = prefer
    req = urllib.request.Request(url, data=json.dumps(corps).encode() if corps is not None else None,
                                 headers=entetes, method=methode)
    with urllib.request.urlopen(req, timeout=30) as r:
        texte = r.read().decode()
        return json.loads(texte) if texte else []


# ---------------------------------------------------------------- statistiques
def _total(metrique: str, depuis: int, jusqua: int) -> int | None:
    r = graph(f"{IG}/insights", metric=metrique, period="day", metric_type="total_value",
              since=depuis, until=jusqua)
    try:
        return int(r["data"][0]["total_value"]["value"])
    except (KeyError, IndexError, TypeError):
        return None


def stats() -> None:
    compte = graph(IG, fields="followers_count,media_count")
    maintenant = int(dt.datetime.now().timestamp())
    il_y_a_7j = maintenant - 7 * 86400
    ligne = {"reseau": "instagram", "abonnes": compte.get("followers_count"),
             "publications": compte.get("media_count"),
             "portee_7j": _total("reach", il_y_a_7j, maintenant),
             "vues_7j": _total("views", il_y_a_7j, maintenant),
             "visites_profil_7j": _total("profile_views", il_y_a_7j, maintenant),
             "clics_site_7j": _total("website_clicks", il_y_a_7j, maintenant),
             "maj_le": dt.datetime.now(dt.timezone.utc).isoformat()}
    supabase("POST", "alluxe_ia_compte", [ligne], prefer="resolution=merge-duplicates")

    medias = graph(f"{IG}/media", fields="id,caption,media_product_type,media_type,permalink,"
                                         "thumbnail_url,media_url,timestamp,like_count,comments_count",
                   limit=40).get("data", [])
    lignes = []
    for m in medias:
        reel = m.get("media_product_type") == "REELS"
        metriques = "reach,views,saved,shares" + (",ig_reels_avg_watch_time" if reel else "")
        ins = graph(f"{m['id']}/insights", metric=metriques)
        v = {d["name"]: d["values"][0]["value"] for d in ins.get("data", [])}
        lignes.append({
            "media_id": m["id"], "reseau": "instagram",
            "type": "REEL" if reel else ("CARROUSEL" if m.get("media_type") == "CAROUSEL_ALBUM" else "PHOTO"),
            "legende": (m.get("caption") or "")[:1500], "lien": m.get("permalink"),
            "vignette": m.get("thumbnail_url") or (m.get("media_url") if not reel else None),
            "publie_le": m.get("timestamp"), "portee": v.get("reach"), "vues": v.get("views"),
            "likes": m.get("like_count"), "commentaires": m.get("comments_count"),
            "enregistrements": v.get("saved"), "partages": v.get("shares"),
            "duree_moyenne_s": round(v["ig_reels_avg_watch_time"] / 1000, 1) if v.get("ig_reels_avg_watch_time") else None,
            "maj_le": dt.datetime.now(dt.timezone.utc).isoformat()})
    if lignes:
        supabase("POST", "alluxe_ia_medias", lignes, prefer="resolution=merge-duplicates")
    print(f"stats : {ligne['abonnes']} abonnés, {len(lignes)} publications à jour")


# ------------------------------------------------------- assistant commentaires
def _francais(texte: str) -> bool:
    mots = set(re.findall(r"[a-zàâçéèêëîïôûùüÿœ']+", texte.lower()))
    return len(mots & MOTS_FR) >= 4


def _candidats() -> list[dict]:
    vus, sortie = set(), []
    limite = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=48)
    for h in HASHTAGS:
        r = graph("ig_hashtag_search", user_id=IG, q=h)
        if not r.get("data"):
            continue
        hid = r["data"][0]["id"]
        for flux in ("recent_media", "top_media"):
            for m in graph(f"{hid}/{flux}", user_id=IG, limit=30,
                           fields="id,caption,permalink,like_count,comments_count,timestamp").get("data", []):
                quand = dt.datetime.fromisoformat(m["timestamp"].replace("+0000", "+00:00"))
                legende = m.get("caption") or ""
                if m["permalink"] in vus or quand < limite or not _francais(legende):
                    continue
                vus.add(m["permalink"])
                m["hashtag"] = h
                sortie.append(m)
    # Les plus vus d'abord, mais où un commentaire se voit encore (pas noyé dans 500 autres).
    sortie.sort(key=lambda m: (m.get("like_count") or 0) / (1 + (m.get("comments_count") or 0) / 50), reverse=True)
    return sortie


def _consigne(legende: str) -> str:
    return (
        "Tu écris UN commentaire Instagram pour @alluxe.ia, quelqu'un qui n'est pas développeur "
        "et construit des systèmes réels avec l'IA (un robot, un labo, une appli, un agent). "
        "Le commentaire sera posté À LA MAIN par lui sous le post ci-dessous.\n"
        "Règles : en français, 1 à 2 phrases, 25 mots maximum ; réagir précisément au contenu du post "
        "(une idée concrète, une question sincère ou une expérience vécue) ; ton naturel, pas de flatterie "
        "vide (« super post », « incroyable ») ; aucun lien, aucune autopromotion, pas de « va voir mon compte » ; "
        "0 ou 1 émoji. Si le post n'est pas en rapport avec l'IA ou la tech, ou est trop vague, réponds "
        "exactement PASSER.\n\nLégende du post :\n" + legende[:1500])


def _par_claude(consigne: str) -> str:
    import anthropic
    r = anthropic.Anthropic().messages.create(model=MODELE, max_tokens=150,
                                              messages=[{"role": "user", "content": consigne}])
    return "".join(b.text for b in r.content if getattr(b, "type", "") == "text")


def _par_openai(consigne: str) -> str:
    req = urllib.request.Request("https://api.openai.com/v1/chat/completions", method="POST",
                                 data=json.dumps({"model": "gpt-4.1-mini", "max_tokens": 150,
                                                  "messages": [{"role": "user", "content": consigne}]}).encode(),
                                 headers={"authorization": "Bearer " + os.environ["OPENAI_API_KEY"],
                                          "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)["choices"][0]["message"]["content"]


def _commentaire(legende: str) -> str | None:
    """Claude d'abord ; OpenAI si Claude refuse (7 oct. : crédit Anthropic épuisé)."""
    consigne = _consigne(legende)
    texte = ""
    for redacteur in (_par_claude, _par_openai):
        try:
            texte = redacteur(consigne)
            break
        except Exception as e:  # noqa: BLE001 -- on essaie le suivant
            print(f"  ({redacteur.__name__} indisponible : {str(e)[:80]})", file=sys.stderr)
    texte = texte.strip().strip('"')
    return None if not texte or texte.upper().startswith("PASSER") else texte


def cibles(essai: bool) -> None:
    deja = {c["lien"] for c in supabase("GET", "alluxe_ia_cibles", requete="?select=lien&limit=2000")}
    retenus = []
    for m in _candidats():
        if m["permalink"] in deja:
            continue
        texte = _commentaire(m.get("caption") or "")
        if not texte:
            continue
        retenus.append({"lien": m["permalink"], "legende": (m.get("caption") or "")[:600],
                        "likes": m.get("like_count"), "commentaires": m.get("comments_count"),
                        "publie_le": m.get("timestamp"), "hashtag": m["hashtag"],
                        "commentaire_propose": texte})
        if len(retenus) >= NB_CIBLES:
            break
    for c in retenus:
        print(f"- {c['likes']} ♥ {c['lien']}\n  → {c['commentaire_propose']}")
    if essai:
        print(f"\nESSAI : {len(retenus)} cible(s), rien n'est enregistré.")
        return
    if retenus:
        supabase("POST", "alluxe_ia_cibles", retenus, prefer="resolution=ignore-duplicates")
    print(f"{len(retenus)} cible(s) envoyée(s) à l'appli")


# ------------------------------------------------------------- Reels à publier
def a_publier(ident: str, fichier: str, titre: str, legende: str, reseau: str, musique: str) -> None:
    chemin = f"alluxe_ia/a_publier/{ident.replace(':', '-')}.mp4"
    url = os.environ["SUPABASE_URL"].rstrip("/") + f"/storage/v1/object/luna/{chemin}"
    cle = os.environ["SUPABASE_SERVICE_KEY"]
    with open(fichier, "rb") as f:
        req = urllib.request.Request(url, data=f.read(), method="POST", headers={
            "apikey": cle, "authorization": f"Bearer {cle}", "content-type": "video/mp4", "x-upsert": "true"})
    urllib.request.urlopen(req, timeout=180)
    supabase("POST", "alluxe_ia_a_publier", [{"id": ident, "titre": titre, "reseau": reseau, "chemin_video": chemin,
                                              "legende": legende, "musique": musique, "statut": "a_publier"}],
             prefer="resolution=merge-duplicates")
    print(f"à publier : {ident} -> {chemin}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sous = ap.add_subparsers(dest="action", required=True)
    sous.add_parser("stats")
    c = sous.add_parser("cibles"); c.add_argument("--essai", action="store_true")
    p = sous.add_parser("a-publier")
    p.add_argument("ident"); p.add_argument("fichier"); p.add_argument("--titre", required=True)
    p.add_argument("--legende-fichier", required=True); p.add_argument("--reseau", default="instagram")
    p.add_argument("--musique", default="")
    a = ap.parse_args()
    _env()
    if a.action == "stats":
        stats()
    elif a.action == "cibles":
        cibles(a.essai)
    else:
        with open(a.legende_fichier, encoding="utf-8") as f:
            a_publier(a.ident, a.fichier, a.titre, f.read().strip(), a.reseau, a.musique)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
