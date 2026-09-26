"""Les deux cerveaux consultes par l'Agent : ChatGPT et Claude.

CE QUE CES TESTS GARDENT, et ce n'est pas la qualite des reponses.

L'architecture demandee par l'operateur le 26 septembre tient sur une
seule propriete : les cerveaux n'ont AUCUN outil. Ils recoivent du
texte, ils rendent du texte. Un modele sans mains ne peut pas desarmer
un garde-fou, quoi qu'on lui ecrive.

Si quelqu'un ajoute un jour `tools` a l'un de ces appels — pour lui
faire lire un fichier, « juste pour l'aider » — toute la securite tombe
sans qu'aucun autre test ne s'en apercoive. D'ou le premier bloc.
"""
from __future__ import annotations

import json

import pytest

from luna import cerveaux


class TestLesCerveauxN_ONT_AUCUN_OUTIL:
    """La propriete sur laquelle repose toute l'architecture."""

    def _corps_envoye(self, monkeypatch, fonction, cle_env, valeur):
        captures = {}

        def faux_poster(url, corps, entetes):
            captures["url"] = url
            captures["corps"] = corps
            captures["entetes"] = entetes
            return valeur

        monkeypatch.setenv(cle_env, "cle-de-test")
        monkeypatch.setattr(cerveaux, "_poster", faux_poster)
        fonction("une question")
        return captures

    def test_chatgpt_ne_recoit_pas_d_outils(self, monkeypatch):
        c = self._corps_envoye(
            monkeypatch, cerveaux.demander_chatgpt, "OPENAI_API_KEY",
            {"choices": [{"message": {"content": "reponse"}}]})
        for interdit in ("tools", "functions", "tool_choice"):
            assert interdit not in c["corps"], (
                f"'{interdit}' donnerait des mains a un cerveau qui ne doit "
                "pas en avoir — toute la securite de l'architecture repose "
                "sur son absence")

    def test_claude_ne_recoit_pas_d_outils(self, monkeypatch):
        c = self._corps_envoye(
            monkeypatch, cerveaux.demander_claude, "ANTHROPIC_API_KEY",
            {"content": [{"type": "text", "text": "reponse"}]})
        assert "tools" not in c["corps"]

    def test_le_cadre_leur_dit_qu_ils_n_ont_pas_d_acces(self):
        # Un modele a qui l'on demande une action repond volontiers comme
        # s'il allait l'executer. Le cadre coupe court.
        assert "AUCUN outil" in cerveaux.CADRE
        assert "l'agent decide et agit" in cerveaux.CADRE


class TestLesClesNeFuientPas:
    def test_chaque_cerveau_n_envoie_que_SA_cle(self, monkeypatch):
        captures = {}
        monkeypatch.setattr(cerveaux, "_poster",
                            lambda u, c, e: captures.update(entetes=e) or
                            {"content": [{"type": "text", "text": "x"}]})
        monkeypatch.setenv("ANTHROPIC_API_KEY", "cle-anthropic")
        monkeypatch.setenv("OPENAI_API_KEY", "cle-openai")
        cerveaux.demander_claude("q")
        envoye = json.dumps(captures["entetes"])
        assert "cle-anthropic" in envoye
        assert "cle-openai" not in envoye, "la cle OpenAI est partie chez Anthropic"


class TestUnCerveauAbsentN_ARRETE_PAS_LES_AUTRES:
    def test_une_panne_n_empeche_pas_le_second_avis(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "cle")
        monkeypatch.setattr(cerveaux, "_poster",
                            lambda *a: {"content": [{"type": "text",
                                                      "text": "avis de claude"}]})
        r = cerveaux.consulter("q")
        assert r["chatgpt"]["ok"] is False
        assert r["claude"]["ok"] is True, "une analyse vaut mieux que zero"

    def test_un_cerveau_inconnu_ne_casse_rien(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "cle")
        monkeypatch.setattr(cerveaux, "_poster",
                            lambda *a: {"content": [{"type": "text", "text": "x"}]})
        r = cerveaux.consulter("q", lesquels=("claude", "gemini"))
        assert r["claude"]["ok"] is True
        assert r["gemini"]["ok"] is False


class TestLesAvisNeSontPasFUSIONNES:
    """Le desaccord est le signal : le masquer perdrait tout l'interet."""

    def test_chaque_avis_garde_son_origine(self):
        resume = cerveaux.resume_consultation({
            "chatgpt": {"ok": True, "reponse": "il faut vendre"},
            "claude": {"ok": True, "reponse": "il faut garder"},
        })
        assert "CHATGPT" in resume and "CLAUDE" in resume
        assert "il faut vendre" in resume and "il faut garder" in resume

    def test_un_injoignable_est_annonce_comme_tel(self):
        resume = cerveaux.resume_consultation({
            "chatgpt": {"ok": False, "erreur": "HTTP 429"},
        })
        assert "INJOIGNABLE" in resume and "429" in resume


class TestLAgentGardeLesDeuxClesEnMemoire:
    def test_sinon_l_outil_marche_a_la_main_et_pas_en_service(self):
        """Le service efface tout secret absent de CLES_UTILES.

        Sans cette entree, `demander_avis` fonctionnerait quand on le
        lance soi-meme et echouerait dans le service — le defaut qui
        passe les tests et tombe en production.
        """
        from ops.agent_alluxe import CLES_UTILES

        for cle in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
            assert cle in CLES_UTILES, (
                f"{cle} serait effacee au demarrage du service et "
                "`demander_avis` echouerait en production")

    def test_les_secrets_dangereux_restent_effaces(self):
        """L'elargissement doit rester borne aux deux cerveaux."""
        from ops.agent_alluxe import CLES_UTILES

        for interdit in ("BITVAVO_API_KEY", "BITVAVO_API_SECRET",
                         "GITHUB_ACTIONS_WRITE_TOKEN", "INSTAGRAM_ACCESS_TOKEN"):
            assert interdit not in CLES_UTILES, (
                f"{interdit} n'a rien a faire en memoire de l'agent")


class TestLOutilRappelleQueCeSontDesAvis:
    def test_il_ne_rend_pas_un_ordre(self, monkeypatch):
        from ops.agent_alluxe import _outil_demander_avis

        monkeypatch.setattr(cerveaux, "consulter",
                            lambda *a, **k: {"claude": {"ok": True,
                                                         "reponse": "vends tout"}})
        r = _outil_demander_avis(None, {"question": "q"})
        assert "AVIS" in r["rappel"] or "avis" in r["rappel"]
        assert "trading reel" in r["rappel"]

    def test_une_question_vide_est_refusee(self):
        from ops.agent_alluxe import _outil_demander_avis

        assert "erreur" in _outil_demander_avis(None, {"question": "  "})
