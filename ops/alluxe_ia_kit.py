#!/usr/bin/env python3
"""alluxe.ia : le robot KIT. Quelqu'un commente KIT -> le kit part en privé.

    python3 ops/alluxe_ia_kit.py abonner              # une fois : brancher le compte au webhook
    python3 ops/alluxe_ia_kit.py etat                 # ce qui est arrivé, ce qui a été envoyé
    python3 ops/alluxe_ia_kit.py traiter              # dit ce qui partirait, n'envoie rien
    python3 ops/alluxe_ia_kit.py traiter --confirmer  # répond vraiment (minuteur, toutes les 30 s)

LA CHAÎNE
  Instagram -> fonction Supabase `alluxe-ia-webhook` (vérifie la signature
  de Meta, dépose dans `alluxe_ia_evenements`) -> ce script (lit la file,
  décide avec alluxe_ia/kit.py, répond avec le jeton Instagram du .env).

  Le jeton Instagram ne quitte jamais le VPS : Supabase n'en a pas besoin.

RIEN NE PART SANS --confirmer, et sans ALLUXE_IA_KIT_URL (le lien du kit)
dans .env : sans lien, il n'y a rien à envoyer.

Variables (.env) : INSTAGRAM_ACCESS_TOKEN, INSTAGRAM_USER_ID, SUPABASE_URL,
SUPABASE_SERVICE_KEY, ALLUXE_IA_KIT_URL, et facultatif ALLUXE_IA_OFFRE_URL
(le lien partenaire du message 3 ; sans lui, le message 3 n'est pas envoyé).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import urllib.parse
import urllib.request

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from alluxe_ia.kit import Action, decider  # noqa: E402

MAX_TENTATIVES = 3
PAR_PASSAGE = 50


def _charger_env() -> None:
    try:
        from gold_bot.env import charger_env
        charger_env()
    except Exception:  # noqa: BLE001 -- le minuteur passe déjà le .env
        pass


class Rest:
    """Client REST Supabase en service_role (les tables n'ont aucune
    politique : elles ne servent qu'à ce script et au webhook)."""

    def __init__(self) -> None:
        self.url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        self.cle = (os.environ.get("SUPABASE_SERVICE_KEY")
                    or os.environ.get("SUPABASE_KEY", ""))
        if not self.url or not self.cle:
            raise SystemExit("SUPABASE_URL / SUPABASE_SERVICE_KEY absents")

    def _req(self, methode: str, chemin: str, corps=None, entetes=None):
        h = {"apikey": self.cle, "authorization": f"Bearer {self.cle}",
             "content-type": "application/json", **(entetes or {})}
        data = json.dumps(corps).encode() if corps is not None else None
        r = urllib.request.Request(f"{self.url}/rest/v1/{chemin}", data=data,
                                   headers=h, method=methode)
        with urllib.request.urlopen(r, timeout=30) as resp:
            brut = resp.read()
        return json.loads(brut) if brut else None

    def a_traiter(self) -> list[dict]:
        return self._req(
            "GET", "alluxe_ia_evenements?traite_at=is.null"
            f"&tentatives=lt.{MAX_TENTATIVES}&order=recu_at.asc&limit={PAR_PASSAGE}") or []

    def contact(self, ig_user_id: str) -> dict | None:
        q = urllib.parse.quote(ig_user_id)
        lignes = self._req("GET", f"alluxe_ia_contacts?ig_user_id=eq.{q}") or []
        return lignes[0] if lignes else None

    def maj_contact(self, ig_user_id: str, champs: dict) -> None:
        if not champs:
            return
        ligne = {k: v for k, v in champs.items() if v is not None}
        ligne.update(ig_user_id=ig_user_id,
                     maj_at=dt.datetime.now(dt.timezone.utc).isoformat())
        self._req("POST", "alluxe_ia_contacts?on_conflict=ig_user_id", ligne,
                  {"prefer": "resolution=merge-duplicates"})

    def marquer(self, ev_id: int, champs: dict) -> None:
        self._req("PATCH", f"alluxe_ia_evenements?id=eq.{ev_id}", champs)

    def compter(self, table: str, filtre: str = "") -> int:
        h = {"prefer": "count=exact", "range": "0-0"}
        r = urllib.request.Request(
            f"{self.url}/rest/v1/{table}?select=*{filtre}",
            headers={"apikey": self.cle, "authorization": f"Bearer {self.cle}", **h})
        with urllib.request.urlopen(r, timeout=30) as resp:
            plage = resp.headers.get("content-range", "*/0")
        return int(plage.split("/")[-1] or 0)


def executer(action: Action) -> None:
    """Un appel à l'API Instagram par action."""
    from ops import instagram as ig
    if action.genre == "reponse_publique":
        ig._appel("POST", f"{action.cible}/replies", message=action.texte)
    elif action.genre == "reponse_privee":
        ig._appel("POST", f"{ig._compte()}/messages",
                  recipient=json.dumps({"comment_id": action.cible}),
                  message=json.dumps({"text": action.texte}, ensure_ascii=False))
    elif action.genre == "message":
        ig._appel("POST", f"{ig._compte()}/messages",
                  recipient=json.dumps({"id": action.cible}),
                  message=json.dumps({"text": action.texte}, ensure_ascii=False))
    else:
        raise ValueError(action.genre)


def traiter(confirmer: bool) -> int:
    lien = os.environ.get("ALLUXE_IA_KIT_URL", "").strip()
    if not lien.startswith("https://"):
        print("ALLUXE_IA_KIT_URL absent ou pas en https : rien à envoyer.")
        return 1
    offre = os.environ.get("ALLUXE_IA_OFFRE_URL", "").strip()
    rest = Rest()
    maintenant = dt.datetime.now(dt.timezone.utc)
    evenements = rest.a_traiter()
    for ev in evenements:
        contact = rest.contact(ev["ig_user_id"])
        d = decider(ev, contact, maintenant, lien, offre)
        qui = ev.get("username") or ev["ig_user_id"]
        if not confirmer:
            print(f"[essai] {ev['type']} de {qui} : {d.resultat}")
            for a in d.actions:
                print(f"         {a.genre} -> {a.texte[:70]!r}")
            continue
        try:
            for a in d.actions:
                executer(a)
        except Exception as exc:  # noqa: BLE001
            n = int(ev.get("tentatives") or 0) + 1
            champs = {"tentatives": n, "resultat": f"erreur : {str(exc)[:300]}"}
            if n >= MAX_TENTATIVES:
                champs["traite_at"] = maintenant.isoformat()
            rest.marquer(ev["id"], champs)
            print(f"ÉCHEC {ev['type']} de {qui} ({n}/{MAX_TENTATIVES}) : {str(exc)[:200]}")
            continue
        rest.maj_contact(ev["ig_user_id"], d.contact)
        rest.marquer(ev["id"], {"traite_at": maintenant.isoformat(),
                                "resultat": d.resultat})
        if d.actions:
            print(f"{ev['type']} de {qui} : {d.resultat}")
    return 0


def abonner() -> int:
    """Demande à Instagram d'envoyer commentaires et messages au webhook."""
    from ops import instagram as ig
    r = ig._appel("POST", "me/subscribed_apps",
                  subscribed_fields="comments,messages")
    print(json.dumps(r, ensure_ascii=False))
    return 0 if r.get("success") else 1


def etat() -> int:
    rest = Rest()
    print(f"évènements reçus    : {rest.compter('alluxe_ia_evenements')}")
    print(f"  en attente        : {rest.compter('alluxe_ia_evenements', '&traite_at=is.null')}")
    print(f"  en erreur         : {rest.compter('alluxe_ia_evenements', '&resultat=like.erreur*')}")
    print(f"kits envoyés        : {rest.compter('alluxe_ia_contacts', '&etape=gte.1')}")
    print(f"ont répondu         : {rest.compter('alluxe_ia_contacts', '&etape=gte.2')}")
    print(f"offre envoyée       : {rest.compter('alluxe_ia_contacts', '&etape=gte.3')}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sous = p.add_subparsers(dest="cmd", required=True)
    t = sous.add_parser("traiter")
    t.add_argument("--confirmer", action="store_true")
    sous.add_parser("abonner")
    sous.add_parser("etat")
    args = p.parse_args()
    _charger_env()
    if args.cmd == "traiter":
        import fcntl
        verrou = open("/tmp/alluxe-ia-kit.lock", "w")
        try:
            fcntl.flock(verrou, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        return traiter(args.confirmer)
    return abonner() if args.cmd == "abonner" else etat()


if __name__ == "__main__":
    raise SystemExit(main())
