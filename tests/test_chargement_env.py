"""Le fichier .env doit etre lu par les commandes, pas seulement par systemd.

Rien, dans le code Python, ne lisait le .env : c'est l'unite systemd qui
l'injecte, par `EnvironmentFile=`. Le service tournait donc avec les cles,
et TOUTE commande lancee a la main tournait sans.

Consequence observee le 29 aout : `run_bot.py check` — la commande dont le
seul role est de verifier l'installation — annoncait « compte : 50.00 EUR »,
le solde fictif du mode sans cle, pour un compte qui en contenait 96. Rien
dans la sortie ne disait pourquoi.

REGLE QUI NE DOIT PAS BOUGER : une variable deja definie n'est jamais
ecrasee. L'environnement du service reste prioritaire sur le fichier.
"""
from __future__ import annotations

import os

from helpers import *  # noqa: F401,F403 - insere la racine du projet dans sys.path

from gold_bot.settings import charger_env


def _ecrire(tmp_path, contenu: str) -> str:
    chemin = tmp_path / ".env"
    chemin.write_text(contenu, encoding="utf-8")
    return str(chemin)


def test_une_variable_simple_est_chargee(tmp_path, monkeypatch):
    monkeypatch.delenv("GB_ESSAI", raising=False)
    assert charger_env(_ecrire(tmp_path, "GB_ESSAI=valeur\n")) == 1
    assert os.environ["GB_ESSAI"] == "valeur"


def test_l_environnement_existant_n_est_JAMAIS_ecrase(tmp_path, monkeypatch):
    """C'est systemd qui decide en production, pas le fichier.

    Sans cette regle, un .env oublie sur le disque pourrait renvoyer un
    robot en argent reel vers d'anciennes cles, en silence.
    """
    monkeypatch.setenv("GB_ESSAI", "celle du service")
    charger_env(_ecrire(tmp_path, "GB_ESSAI=celle du fichier\n"))
    assert os.environ["GB_ESSAI"] == "celle du service"


def test_les_guillemets_sont_retires(tmp_path, monkeypatch):
    monkeypatch.delenv("GB_ESSAI", raising=False)
    charger_env(_ecrire(tmp_path, 'GB_ESSAI="entre guillemets"\n'))
    assert os.environ["GB_ESSAI"] == "entre guillemets"


def test_la_forme_export_est_acceptee(tmp_path, monkeypatch):
    # Ecriture courante dans un .env redige a la main.
    monkeypatch.delenv("GB_ESSAI", raising=False)
    charger_env(_ecrire(tmp_path, "export GB_ESSAI=exportee\n"))
    assert os.environ["GB_ESSAI"] == "exportee"


def test_les_commentaires_et_lignes_vides_sont_ignores(tmp_path, monkeypatch):
    monkeypatch.delenv("GB_ESSAI", raising=False)
    n = charger_env(_ecrire(tmp_path, "# un commentaire\n\nGB_ESSAI=ok\n\n"))
    assert n == 1


def test_une_valeur_contenant_un_egal_reste_entiere(tmp_path, monkeypatch):
    # Les secrets en base64 finissent regulierement par « = ».
    monkeypatch.delenv("GB_ESSAI", raising=False)
    charger_env(_ecrire(tmp_path, "GB_ESSAI=abc=def==\n"))
    assert os.environ["GB_ESSAI"] == "abc=def=="


def test_un_fichier_absent_ne_plante_pas(tmp_path):
    assert charger_env(str(tmp_path / "rien.env")) == 0


def test_une_ligne_sans_egal_est_ignoree(tmp_path, monkeypatch):
    monkeypatch.delenv("GB_ESSAI", raising=False)
    assert charger_env(_ecrire(tmp_path, "ceci n'est pas une variable\n")) == 0


# --------------------------------------------------------------------------
# Le cablage : une fonction non appelee ne sert a rien
# --------------------------------------------------------------------------
def test_les_commandes_chargent_reellement_le_env():
    """Un test qui verifie la fonction SANS verifier qu'on l'appelle
    passerait au vert avec le cablage retire. C'est deja arrive."""
    import inspect

    import etat
    import run_bot
    assert "charger_env()" in inspect.getsource(run_bot.build_config), (
        "build_config est le passage oblige de toutes les commandes")
    assert "charger_env()" in inspect.getsource(etat.main)


def test_le_chargement_ne_journalise_jamais_les_valeurs(tmp_path, monkeypatch, caplog):
    """Ce fichier contient les cles d'API : les lire dans un journal suffit
    a prendre le controle du compte."""
    import logging
    monkeypatch.delenv("GB_SECRET_ESSAI", raising=False)
    with caplog.at_level(logging.DEBUG):
        charger_env(_ecrire(tmp_path, "GB_SECRET_ESSAI=ne-doit-pas-apparaitre\n"))
    assert "ne-doit-pas-apparaitre" not in caplog.text
