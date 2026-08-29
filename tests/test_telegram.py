"""Le canal Telegram doit dire POURQUOI il ne marche pas, sans jamais
montrer le token.

L'operateur ne recevait aucune alerte. Le journal disait « telegram
indisponible : ... HTTP Error 404 », ce qui se lit comme une panne de
Telegram. Ce n'en est pas une : l'adresse d'envoi CONTIENT le token, donc
elle n'existe que si le token existe. Un 404 veut dire que le token ne
correspond a aucun robot — et aucun reessai n'y changera rien.
"""
from __future__ import annotations

import logging

from helpers import *  # noqa: F401,F403 - insere la racine du projet dans sys.path

import gold_bot.notifiers as notifiers
from gold_bot.notifiers import Notification, TelegramChannel, valeur_env

VRAI_TOKEN = "8123456789:AAH0zqVeryLongSecretStringHere_x1"


def canal(monkeypatch, token=VRAI_TOKEN, chat="4242") -> TelegramChannel:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", token)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", chat)
    return TelegramChannel()


# --------------------------------------------------------------------------
# Ce qu'un copier-coller ajoute
# --------------------------------------------------------------------------
def test_les_guillemets_d_un_env_sont_retires(monkeypatch):
    monkeypatch.setenv("T", '"8123456789:AAH0zq"')
    assert valeur_env("T") == "8123456789:AAH0zq"


def test_les_apostrophes_aussi(monkeypatch):
    monkeypatch.setenv("T", "'abc'")
    assert valeur_env("T") == "abc"


def test_les_espaces_de_fin_sont_retirees(monkeypatch):
    # Une espace finale suffit a faire repondre 404 a Telegram.
    monkeypatch.setenv("T", "  8123456789:AAH0zq  \n")
    assert valeur_env("T") == "8123456789:AAH0zq"


def test_une_variable_absente_donne_une_chaine_vide(monkeypatch):
    monkeypatch.delenv("T", raising=False)
    assert valeur_env("T") == ""


# --------------------------------------------------------------------------
# Le diagnostic
# --------------------------------------------------------------------------
def test_un_token_bien_forme_ne_produit_aucun_diagnostic(monkeypatch):
    assert canal(monkeypatch).diagnostic() == ""


def test_un_token_mal_forme_est_nomme_avant_tout_envoi(monkeypatch):
    # Sans ca, le robot tourne des heures avant qu'un premier trade
    # revele que les alertes ne partent pas.
    d = canal(monkeypatch, token="AAH0zqPasDeNumeroDevant").diagnostic()
    assert "mal forme" in d


def test_le_diagnostic_ne_montre_jamais_le_token(monkeypatch):
    d = canal(monkeypatch, token="AAH0zqPasDeNumeroDevant").diagnostic()
    assert "AAH0zq" not in d


def test_le_chat_id_manquant_est_nomme(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", VRAI_TOKEN)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    assert "CHAT_ID" in TelegramChannel().diagnostic()


# --------------------------------------------------------------------------
# Le 404
# --------------------------------------------------------------------------
def _echoue(monkeypatch, message: str) -> None:
    def faux(*a, **k):
        raise RuntimeError(message)
    monkeypatch.setattr(notifiers, "http_json", faux)


def test_un_404_desactive_le_canal_au_lieu_de_reessayer(monkeypatch):
    c = canal(monkeypatch)
    assert c.enabled()
    _echoue(monkeypatch, "HTTP notification indisponible: HTTP Error 404: Not Found")
    c.send(Notification("trade", "essai"))
    assert not c.enabled(), "un token refuse le reste : inutile de reessayer"
    assert "refuse" in c.diagnostic()


def test_le_404_est_explique_comme_un_token_et_non_comme_une_panne(monkeypatch, caplog):
    c = canal(monkeypatch)
    _echoue(monkeypatch, "HTTP Error 404: Not Found")
    with caplog.at_level(logging.ERROR):
        c.send(Notification("trade", "essai"))
    texte = caplog.text
    assert "token refuse" in texte
    assert "BotFather" in texte, "le message doit dire quoi faire"
    assert VRAI_TOKEN not in texte, "le token ne doit jamais atterrir dans un journal"


def test_une_vraie_panne_reseau_ne_desactive_pas_le_canal(monkeypatch):
    # Une coupure passagere doit pouvoir se retablir toute seule.
    c = canal(monkeypatch)
    _echoue(monkeypatch, "HTTP notification indisponible: timed out")
    c.send(Notification("trade", "essai"))
    assert c.enabled()


def test_le_token_est_masque_meme_dans_une_erreur_quelconque(monkeypatch, caplog):
    # urllib met l'URL complete dans ses messages, et l'URL contient le
    # token : sans masquage il se retrouve en clair dans les journaux.
    c = canal(monkeypatch)
    _echoue(monkeypatch, f"echec sur https://api.telegram.org/bot{VRAI_TOKEN}/sendMessage")
    with caplog.at_level(logging.WARNING):
        c.send(Notification("trade", "essai"))
    assert VRAI_TOKEN not in caplog.text
    assert "<token>" in caplog.text
