#!/usr/bin/env python3
"""Planifie automatiquement le contenu Luna des prochaines 24-48h.

Le planificateur :
1. lit les creneaux editoriaux de luna/strategie.py ;
2. recherche un lieu lorsque le creneau en a besoin ;
3. demande au moteur texte une legende + prompt visuel + hook + CTA ;
4. depose les jobs dans luna_publications ;
5. laisse ops/executer_luna.py generer et publier selon l'intention.

Il ne lit jamais .env dans le prompt et ne copie aucune cle dans Supabase.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import json
import os
import urllib.parse
import urllib.request

from gold_bot.env import charger_env
from luna.moments import moment_pour
from luna.strategie import SEMAINE, Slot, construire_prompt

charger_env()


def _rest(chemin: str, methode: str = "GET", corps: dict | None = None) -> list:
    base = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not base or not key:
        raise RuntimeError("Supabase non configure")
    data = json.dumps(corps).encode("utf-8") if corps is not None else None
    req = urllib.request.Request(
        f"{base}/rest/v1/{chemin}",
        data=data,
        headers={"apikey": key, "authorization": f"Bearer {key}",
                 "content-type": "application/json"},
        method=methode,
    )
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.loads(response.read().decode("utf-8") or "[]")


def _recherche_lieu(query: str) -> str:
    try:
        from ops.agent_outils import chercher_sur_le_web
        rep = chercher_sur_le_web({"question": query})
        lignes = rep.get("resultats") or []
        return "\n".join(
            f"- {x.get('titre','')} | {x.get('lien','')}" for x in lignes[:6]
        )
    except Exception as exc:
        return f"Recherche indisponible : {str(exc)[:160]}"


def _moteur():
    from luna.moteurs import choisir_moteur
    return choisir_moteur()


def _json_llm(instruction: str) -> dict:
    systeme = """Tu es le directeur editorial de Luna.
Retourne UNIQUEMENT un objet JSON valide avec les cles :
caption, prompt, hook, call_to_action, hashtags, location_name, location_city.
caption est en francais. prompt est en anglais et decrit une vraie photo/video
de smartphone, adulte, naturel, non studio. hashtags est une liste de 3 a 8
hashtags pertinents sans spam. N'invente aucun prix, horaire ou fait sur un lieu
si la recherche fournie ne le confirme pas."""
    brut = _moteur().repondre(systeme, [{"role": "user", "texte": instruction}])
    debut, fin = brut.find("{"), brut.rfind("}")
    if debut < 0 or fin <= debut:
        raise ValueError("le moteur n'a pas rendu du JSON")
    objet = json.loads(brut[debut:fin + 1])
    if not isinstance(objet, dict):
        raise ValueError("JSON editorial invalide")
    return objet


def _creer_job(dt_cible: datetime, slot: Slot, ville: str,
               recherche: str = "") -> dict:
    lieu_needed = slot.objectif in {
        "lieu_ou_cafe", "decouverte_lieu", "restaurant", "bar_ou_restaurant",
        "restaurant_bar", "food", "sortie", "restaurant_bar"
    }
    question = (
        f"Trouve des lieux reels et photogeniques actuellement pertinents a "
        f"{ville} pour Luna : "
        f"{slot.objectif}. Privilegie restaurant, bar, cafe, monument ou "
        f"quartier interessant. Donne des sources exploitables."
    )
    if lieu_needed and not recherche:
        recherche = _recherche_lieu(question)

    instruction = f"""
Format : {slot.content_format}
Plateforme : {slot.platform}
Objectif : {slot.objectif}
Monetisation : {slot.monetization_track}
Ville de base : {ville}
Duree : {slot.duree} secondes

Contexte de recherche :
{recherche or "(pas de lieu necessaire)"}

Regles :
- Luna est un personnage fictif adulte de 25 ans.
- Le visage doit rester fidele a luna/persona.py.
- Pour une Story, penser vertical 9:16.
- Pour un feed, 3:4.
- Pour un Reel, 9:16.
- Pour TikTok, 9:16.
- Pour tiktok_rewards, ecrire une vraie idee originale pouvant devenir un
  contenu de plus d'une minute ; pas une simple image, pas un diaporama.
- Pour un restaurant/bar/cafe, le lieu est le sujet principal autant que Luna.
- Pas de fausse experience client : utiliser un ton de decouverte et ne pas
  affirmer qu'un lieu a ete visite si ce n'est pas etabli.
- Le contenu IA photorealiste doit rester divulgue comme contenu IA.
"""
    if lieu_needed:
        instruction += f"\nChoisis UN lieu precis a partir des resultats :\n{recherche}\n"
    objet = _json_llm(instruction)
    obj = {
        "type": slot.media_type,
        "content_format": slot.content_format,
        "prompt": str(objet.get("prompt") or "").strip()
                  or construire_prompt(slot, ville=ville),
        "caption": str(objet.get("caption") or "").strip(),
        "aspect_ratio": "9:16" if slot.content_format in {
            "story", "highlight_story", "reel", "tiktok_short", "tiktok_rewards"
        } else "3:4",
        "duration_seconds": slot.duree,
        "quality": "finale",
        "publish": True,
    }
    if slot.content_format == "tiktok_rewards":
        obj["duration_seconds"] = max(60, slot.duree)
    source_job = f"{dt_cible.strftime('%Y%m%d-%H%M')}-{slot.platform}-{slot.content_format}"
    payload = {
        "demande": json.dumps(obj, ensure_ascii=False),
        "media_type": slot.media_type,
        "aspect_ratio": obj["aspect_ratio"],
        "duration_seconds": obj["duration_seconds"],
        "quality": "finale",
        "publish_requested": True,
        "content_format": slot.content_format,
        "platform": slot.platform,
        "scheduled_at": dt_cible.isoformat(),
        "timezone": "Europe/Paris",
        "location_name": objet.get("location_name") or None,
        "location_city": objet.get("location_city") or ville,
        "location_type": _location_type(slot),
        "hook": str(objet.get("hook") or "").strip() or None,
        "call_to_action": str(objet.get("call_to_action") or "").strip() or None,
        "hashtags": objet.get("hashtags") if isinstance(objet.get("hashtags"), list) else [],
        "ai_disclosure": True,
        "monetization_track": slot.monetization_track,
        "strategy_version": "2026-09",
        "source_job": source_job,
        "highlight_name": (
            objet.get("location_city") or ville
            if slot.content_format == "highlight_story" else None
        ),
    }
    return payload


def _location_type(slot: Slot) -> str | None:
    if slot.objectif in {"restaurant", "bar_ou_restaurant", "restaurant_bar", "food"}:
        return "restaurant"
    if slot.objectif in {"lieu_ou_cafe", "cafe_travail"}:
        return "cafe"
    if slot.objectif in {"decouverte_lieu", "lieu_photo", "avant_apres_lieu"}:
        return "landmark"
    if slot.objectif in {"sortie", "vlog_sortie", "weekend"}:
        return "travel"
    return None


def main() -> int:
    base = datetime.now(ZoneInfo("Europe/Paris"))
    fin = base + timedelta(hours=36)

    villes = [x.strip() for x in os.getenv(
        "LUNA_VILLES", "Metz,Paris,Strasbourg,Luxembourg"
    ).split(",") if x.strip()]
    ville_cycle = iter(villes)
    creees = 0

    for delta in range(3):
        jour = base + timedelta(days=delta)
        for slot in SEMAINE[jour.weekday()]:
            hh, mm = (int(x) for x in slot.heure.split(":"))
            cible = jour.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if cible < base or cible > fin:
                continue

            filt = urllib.parse.quote(
                f"platform=eq.{slot.platform}&content_format=eq.{slot.content_format}"
                f"&scheduled_at=eq.{cible.isoformat()}&select=id",
                safe="=&,.:+-"
            )
            existants = _rest(f"luna_publications?{filt}")
            if existants:
                continue

            # Les sorties/lieux tournent entre les villes configurees.
            ville = next(ville_cycle, villes[0])
            try:
                payload = _creer_job(cible, slot, ville)
                _rest("luna_publications", "POST", payload)
                print(f"job cree : {cible.isoformat()} {slot.platform}/{slot.content_format}")
                creees += 1
            except Exception as exc:
                print(f"job ignore {cible.isoformat()} : {str(exc)[:220]}")

    print(f"{creees} job(s) Luna planifie(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
