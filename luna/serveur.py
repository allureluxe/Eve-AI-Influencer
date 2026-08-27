"""L'application : un serveur HTTP local, sans aucune dependance.

    python3 luna.py app        puis  http://127.0.0.1:8765

Il sert l'interface (messages, appel, visio) et une petite API JSON.
Volontairement en `http.server` : ca demarre en une seconde, ca tourne sur
n'importe quelle machine, et il n'y a rien a installer avant de parler a
Luna.

Deux precautions, parce que le contenu est intime :

- l'ecoute est sur 127.0.0.1 par defaut : rien ne sort de la machine ;
- si tu l'exposes sur ton reseau (--hote 0.0.0.0), LUNA_TOKEN devient
  obligatoire et chaque requete doit le presenter.
"""
from __future__ import annotations

import json
import mimetypes
import os
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import limites
from .avatar import (AMBIANCES, JEUX, TENUES, FournisseurAvatar, demarrer_visio)
from .chat import Luna
from .memoire import Memoire
from .moments import MOMENTS
from .moteurs import ErreurMoteur, GenerateurImages
from .persona import LUNA
from .photos import prompt_photo, scenes_autorisees
from .voix import ANNONCE_IA, FournisseurVoix, profil_pour

WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
DOSSIER_DONNEES = os.getenv("LUNA_DONNEES", "data/luna")


def _fichier(nom: str) -> str:
    return os.path.join(DOSSIER_DONNEES, nom)


class Application:
    """L'etat partage du serveur. Un seul utilisateur : toi."""

    def __init__(self):
        self.porte = limites.PorteAdulte(_fichier("acces.json"))
        self.luna = Luna(memoire=Memoire(_fichier("memoire.json")), porte=self.porte)
        self.images = GenerateurImages()
        self.voix = FournisseurVoix()
        self.avatar = FournisseurAvatar()

    # -- vues -------------------------------------------------------------
    def etat(self) -> dict:
        moment = self.luna.moment()
        registre = self.luna.registre_effectif("app")
        return {
            "persona": {
                "prenom": LUNA.prenom, "age": LUNA.age, "taille": LUNA.taille_cm,
                "metier": LUNA.metier,
                "caractere": list(LUNA.caractere), "passions": list(LUNA.passions),
            },
            "moment": {"cle": moment.cle, "nom": moment.nom,
                       "ambiance": moment.ambiance, "tenue": moment.tenue},
            "moments": [{"cle": m.cle, "nom": m.nom, "sur_demande": m.sur_demande}
                        for m in MOMENTS.values()],
            "registre": registre,
            "registre_demande": self.luna.registre_demande,
            "acces": self.porte.acces.en_dict(),
            "moteur": {"nom": self.luna.moteur.nom,
                       "disponible": bool(self.luna.moteur.disponible)},
            "capacites": {
                "images": self.images.disponible,
                "voix_externe": self.voix.disponible,
                "avatar": self.avatar.configuration(),
            },
            "memoire": {"prenom": self.luna.memoire.prenom,
                        "resume": self.luna.memoire.resume(),
                        "rencontres": self.luna.memoire.rencontres},
            "tenues": [{"cle": t.cle, "nom": t.nom, "registre": t.registre,
                        "couleurs": list(t.couleurs), "description": t.description}
                       for t in TENUES],
            "ambiances": [{"cle": a.cle, "nom": a.nom, "fond": list(a.fond),
                           "lumiere": a.lumiere, "musique": a.musique}
                          for a in AMBIANCES],
            "jeux": [{"cle": c, "nom": n, "resume": r} for c, n, r in JEUX],
            "scenes": [{"cle": s.cle, "titre": s.titre, "registre": s.registre}
                       for s in scenes_autorisees(limites.ADULTE)],
            "annonce_ia": ANNONCE_IA,
            "historique": self.luna.memoire.historique(20),
        }

    # -- actions ----------------------------------------------------------
    def message(self, corps: dict) -> dict:
        reponse = self.luna.repondre(str(corps.get("texte", "")),
                                     canal=str(corps.get("canal", "app")))
        return {
            "texte": reponse.texte, "moment": reponse.moment,
            "registre": reponse.registre, "expression": reponse.expression,
            "voix": reponse.voix, "signaux": reponse.signaux,
            "erreur": reponse.erreur,
        }

    def ouverture(self, corps: dict) -> dict:
        r = self.luna.ouverture(canal=str(corps.get("canal", "app")))
        return {"texte": r.texte, "moment": r.moment, "registre": r.registre,
                "expression": r.expression, "voix": r.voix}

    def acces(self, corps: dict) -> dict:
        if corps.get("revoquer"):
            self.porte.revoquer()
        elif corps.get("majeur"):
            self.porte.confirmer(
                methode=str(corps.get("methode", "declaratif")),
                registre_max=str(corps.get("registre_max", limites.SENSUEL)))
        return self.etat()

    def registre(self, corps: dict) -> dict:
        self.luna.demander_registre(str(corps.get("registre", limites.SENSUEL)))
        return self.etat()

    def moment(self, corps: dict) -> dict:
        cle = str(corps.get("cle", ""))
        if cle == "auto":
            self.luna.relacher_moment()
        elif cle in MOMENTS:
            demande = MOMENTS[cle]
            if demande.sur_demande and not self.porte.acces.ouvert_pour(limites.SENSUEL):
                return {"erreur": "acces_refuse",
                        "message": "La soiree privee demande la confirmation 18+."}
            self.luna.forcer_moment(cle)
        return self.etat()

    def visio(self, corps: dict) -> dict:
        registre = self.luna.registre_effectif("visio")
        session = demarrer_visio(self.luna.moment(), registre,
                                 tenue=str(corps.get("tenue", "")),
                                 ambiance=str(corps.get("ambiance", "")))
        return {
            "tenue": {"cle": session.tenue.cle, "nom": session.tenue.nom,
                      "couleurs": list(session.tenue.couleurs),
                      "description": session.tenue.description,
                      "scene": session.tenue.scene},
            "ambiance": {"cle": session.ambiance.cle, "nom": session.ambiance.nom,
                         "fond": list(session.ambiance.fond),
                         "lumiere": session.ambiance.lumiere,
                         "musique": session.ambiance.musique},
            "expression": session.expression,
            "ouverture": session.ouverture,
            "registre": session.registre,
            "fournisseur": self.avatar.configuration(),
            "voix": profil_pour(self.luna.moment().cle).en_dict(),
            "jeux": [{"cle": c, "nom": n, "resume": r} for c, n, r in session.jeux],
        }

    def photo(self, corps: dict) -> dict:
        registre = self.luna.registre_effectif("app")
        try:
            demande = prompt_photo(str(corps.get("scene", "")), registre)
        except KeyError as e:
            return {"erreur": "scene_inconnue", "message": str(e)}
        except PermissionError as e:
            return {"erreur": "acces_refuse", "message": str(e)}
        if not self.images.disponible:
            demande["image"] = ""
            demande["message"] = ("Aucun generateur d'images configure : voici le "
                                  "prompt, pret a coller ailleurs.")
            return demande

        import base64
        cache = _fichier(os.path.join("photos", demande["scene"] + ".png"))
        if not corps.get("regenerer") and os.path.exists(cache):
            with open(cache, "rb") as f:
                demande["image"] = "data:image/png;base64," + base64.b64encode(f.read()).decode()
            demande["cache"] = True
            return demande
        try:
            brut = self.images.generer(demande["prompt"], demande["negatif"],
                                       demande["graine"])
        except ErreurMoteur as e:
            demande["image"] = ""
            demande["message"] = f"Generation impossible : {e}"
            return demande
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        with open(cache, "wb") as f:
            f.write(brut)
        demande["image"] = "data:image/png;base64," + base64.b64encode(brut).decode()
        demande["cache"] = False
        return demande

    def parler(self, corps: dict) -> dict:
        """Synthese vocale par prestataire, si configure."""
        texte = str(corps.get("texte", ""))
        if not self.voix.disponible:
            return {"audio": "", "message": "voix du navigateur"}
        try:
            brut = self.voix.parler(texte)
        except RuntimeError as e:
            return {"audio": "", "message": str(e)}
        import base64
        return {"audio": "data:audio/mpeg;base64," + base64.b64encode(brut).decode()}

    def oublier(self, corps: dict) -> dict:
        self.luna.memoire.oublier(str(corps.get("categorie", "")))
        return self.etat()


class Poignee(BaseHTTPRequestHandler):
    application: Application
    jeton: str = ""
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):  # silence : pas de log intime
        pass

    # -- utilitaires ------------------------------------------------------
    def _repondre_json(self, donnees: dict, code: int = 200) -> None:
        brut = json.dumps(donnees, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(brut)))
        self.send_header("cache-control", "no-store")
        self.end_headers()
        self.wfile.write(brut)

    def _autorise(self, requete) -> bool:
        if not self.jeton:
            return True
        entete = self.headers.get("x-luna-token", "")
        depuis_url = parse_qs(requete.query).get("token", [""])[0]
        return secrets.compare_digest(entete or depuis_url, self.jeton)

    def _servir_fichier(self, chemin: str) -> None:
        complet = os.path.normpath(os.path.join(WEB, chemin.lstrip("/")))
        if not complet.startswith(WEB) or not os.path.isfile(complet):
            self.send_error(404)
            return
        type_mime = mimetypes.guess_type(complet)[0] or "application/octet-stream"
        with open(complet, "rb") as f:
            brut = f.read()
        self.send_response(200)
        self.send_header("content-type", type_mime)
        self.send_header("content-length", str(len(brut)))
        self.end_headers()
        self.wfile.write(brut)

    # -- routes -----------------------------------------------------------
    def do_GET(self):
        requete = urlparse(self.path)
        if not self._autorise(requete):
            self._repondre_json({"erreur": "jeton"}, 401)
            return
        if requete.path in ("/", "/index.html"):
            self._servir_fichier("index.html")
        elif requete.path == "/api/etat":
            self._repondre_json(self.application.etat())
        elif requete.path.startswith("/web/"):
            self._servir_fichier(requete.path[5:])
        else:
            self.send_error(404)

    def do_POST(self):
        requete = urlparse(self.path)
        if not self._autorise(requete):
            self._repondre_json({"erreur": "jeton"}, 401)
            return
        taille = int(self.headers.get("content-length", 0) or 0)
        try:
            corps = json.loads(self.rfile.read(taille) or b"{}")
        except ValueError:
            self._repondre_json({"erreur": "json"}, 400)
            return
        if not isinstance(corps, dict):
            corps = {}

        routes = {
            "/api/message": self.application.message,
            "/api/ouverture": self.application.ouverture,
            "/api/acces": self.application.acces,
            "/api/registre": self.application.registre,
            "/api/moment": self.application.moment,
            "/api/visio": self.application.visio,
            "/api/photo": self.application.photo,
            "/api/parler": self.application.parler,
            "/api/oublier": self.application.oublier,
        }
        action = routes.get(requete.path)
        if action is None:
            self.send_error(404)
            return
        try:
            self._repondre_json(action(corps))
        except ValueError as e:
            self._repondre_json({"erreur": "requete", "message": str(e)}, 400)


def lancer(hote: str = "127.0.0.1", port: int = 8765) -> None:
    jeton = os.getenv("LUNA_TOKEN", "")
    if hote not in ("127.0.0.1", "localhost", "::1") and not jeton:
        raise SystemExit(
            "Refus d'ecouter sur " + hote + " sans jeton.\n"
            "  Une conversation intime accessible a tout le reseau local, "
            "c'est non.\n"
            "  Definis LUNA_TOKEN dans .env, puis ouvre "
            "http://<ip>:%d/?token=<jeton>" % port)

    Poignee.application = Application()
    Poignee.jeton = jeton
    serveur = ThreadingHTTPServer((hote, port), Poignee)
    adresse = f"http://{hote}:{port}"
    if jeton:
        adresse += f"/?token={jeton}"
    print(f"Luna est en ligne : {adresse}")
    print(f"Moteur : {Poignee.application.luna.moteur.nom}   "
          f"(Ctrl+C pour arreter)")
    try:
        serveur.serve_forever()
    except KeyboardInterrupt:
        print("\nA tout a l'heure ❤️")
    finally:
        serveur.server_close()
