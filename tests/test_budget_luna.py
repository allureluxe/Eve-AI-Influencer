"""Le plafond de depense de Luna : il doit REFUSER, pas prevenir.

Ce compteur est le seul obstacle entre une boucle automatique qui tourne
toutes les deux minutes et une facture OpenAI/Runway. Les tests ci-dessous
verifient qu'il refuse dans les quatre situations ou un plafond mal ecrit
laisse passer : quand le total depasse, quand le processus redemarre,
quand la journee change, et quand il ne sait plus ou il en est.
"""
from __future__ import annotations

import json

import pytest

from luna.budget import BudgetEpuise, Depenses


@pytest.fixture
def fichier(tmp_path):
    return tmp_path / "depenses.json"


class TestLePlafondRefuse:
    def test_il_laisse_passer_sous_le_plafond(self, fichier):
        d = Depenses(plafond_eur=1.00, fichier=fichier)
        assert d.reserver(0.30, "image") == pytest.approx(0.70)
        assert d.total_du_jour() == pytest.approx(0.30)

    def test_il_refuse_au_dela_et_NE_DEPENSE_RIEN(self, fichier):
        d = Depenses(plafond_eur=0.20, fichier=fichier)
        d.reserver(0.15, "image")
        with pytest.raises(BudgetEpuise):
            d.reserver(0.10, "image de trop")
        # LE POINT QUI COMPTE : l'operation refusee ne doit pas etre
        # comptee. Un compteur qui s'incremente sur un refus finirait par
        # bloquer une journee entiere pour des depenses jamais faites.
        assert d.total_du_jour() == pytest.approx(0.15)

    def test_le_refus_dit_combien_et_pourquoi(self, fichier):
        d = Depenses(plafond_eur=0.10, fichier=fichier)
        with pytest.raises(BudgetEpuise, match="LUNA_BUDGET_JOUR_EUR"):
            d.reserver(0.50, "video")


class TestLeCompteurSurvitAuProcessus:
    def test_deux_instances_partagent_le_meme_total(self, fichier):
        # Le cron lance un PROCESSUS NEUF toutes les deux minutes. Un
        # compteur en memoire repartirait de zero a chaque fois, ce qui
        # revient exactement a n'avoir aucun plafond.
        Depenses(plafond_eur=1.00, fichier=fichier).reserver(0.60, "premiere")
        seconde = Depenses(plafond_eur=1.00, fichier=fichier)
        assert seconde.total_du_jour() == pytest.approx(0.60)
        with pytest.raises(BudgetEpuise):
            seconde.reserver(0.50, "seconde")

    def test_un_autre_jour_remet_le_compteur_a_zero(self, fichier):
        fichier.write_text(json.dumps(
            {"date": "2020-01-01", "total_eur": 99.0, "lignes": []}),
            encoding="utf-8")
        d = Depenses(plafond_eur=1.00, fichier=fichier)
        assert d.total_du_jour() == 0.0
        assert d.reserver(0.50, "nouveau jour") == pytest.approx(0.50)


class TestIlRefuseQuandIlNeSaitPas:
    """« Un garde-fou qui ne peut pas verifier doit refuser » — CLAUDE.md."""

    def test_un_fichier_illisible_bloque_la_depense(self, fichier):
        fichier.write_text("{ceci n'est pas du JSON", encoding="utf-8")
        d = Depenses(plafond_eur=10.0, fichier=fichier)
        with pytest.raises(BudgetEpuise, match="illisible"):
            d.reserver(0.01, "apres corruption")

    def test_un_fichier_au_mauvais_format_bloque_aussi(self, fichier):
        fichier.write_text("[1, 2, 3]", encoding="utf-8")
        d = Depenses(plafond_eur=10.0, fichier=fichier)
        with pytest.raises(BudgetEpuise, match="format"):
            d.reserver(0.01, "liste au lieu d'objet")

    def test_mais_un_fichier_ABSENT_est_normal(self, fichier):
        # Premier appel de la journee : rien a lire, et c'est juste.
        assert not fichier.exists()
        d = Depenses(plafond_eur=1.00, fichier=fichier)
        assert d.reserver(0.10, "premiere du jour") == pytest.approx(0.90)


class TestLesMoteursPayantsPassentParLa:
    def test_le_generateur_openai_refuse_quand_le_budget_est_plein(
            self, fichier, monkeypatch):
        # Le repli doit fonctionner : un budget plein est une panne comme
        # une autre, la chaine passe au fournisseur gratuit suivant. Elle
        # ne doit PAS s'arreter.
        from luna.moteurs import ErreurMoteur, GenerateurImages

        monkeypatch.setenv("LUNA_DEPENSES_FICHIER", str(fichier))
        monkeypatch.setenv("LUNA_BUDGET_JOUR_EUR", "0.01")
        monkeypatch.setenv("LUNA_COUT_IMAGE_EUR", "0.07")
        monkeypatch.setattr("luna.budget.FICHIER", fichier)

        g = GenerateurImages.__new__(GenerateurImages)
        g.modele = "gpt-image-1"
        with pytest.raises(ErreurMoteur, match="plafond"):
            g._generer_openai("sk-test", "https://api.openai.com/v1/images/generations",
                              "une photo", "", 0, "portrait")
