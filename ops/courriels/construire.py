"""Construit les courriels d'Alluxe a partir d'UN SEUL gabarit.

POURQUOI UN GENERATEUR PLUTOT QUE QUATRE FICHIERS. Ces messages ne
different que par trois phrases. Recopies a la main, ils divergent : on
corrige le logo dans l'un, la couleur dans un autre, et six mois plus
tard l'utilisateur qui reinitialise son mot de passe recoit un courriel
d'une autre marque que celui qui s'inscrit. C'est exactement ce que le
CLAUDE.md reproche aux textes recopies a la main.

    python3 ops/courriels/construire.py            # ecrit les fichiers
    python3 ops/courriels/construire.py --publier  # les installe aussi

`{{ .ConfirmationURL }}` est remplace par Supabase au moment de l'envoi.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

LOGO = ("https://jwksajhtvhwktkbkpits.supabase.co"
        "/storage/v1/object/public/marque/logo.png")

# Le jaune ADOUCI pour les aplats, le jaune PUR pour les petites traces.
# Retour de l'operateur le 19 sept. : le jaune du logo « attaque les
# yeux » des qu'il couvre une surface. Voir `theme.ts`.
JAUNE_APLAT = "#EDEF3A"
JAUNE_PUR = "#FCFF00"
ENCRE = "#15150F"

GABARIT = """<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
       style="background:#F4F4F0;margin:0;padding:32px 12px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
  <tr><td align="center">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
           style="max-width:520px;background:#FFFFFF;border:1px solid #E2E2DA;border-radius:14px;overflow:hidden;">
      <tr><td style="height:5px;background:{aplat};font-size:0;line-height:0;">&nbsp;</td></tr>
      <tr><td align="center" style="padding:34px 32px 0 32px;">
        <img src="{logo}" width="88" height="86" alt="Alluxe"
             style="display:block;border:0;outline:none;text-decoration:none;">
      </td></tr>
      <tr><td align="center" style="padding:18px 32px 0 32px;">
        <div style="font-size:13px;letter-spacing:3px;text-transform:uppercase;color:#8A8A7E;font-weight:600;">Alluxe</div>
      </td></tr>
      <tr><td align="center" style="padding:14px 32px 0 32px;">
        <h1 style="margin:0;font-size:25px;line-height:1.25;color:{encre};font-weight:700;letter-spacing:-0.3px;">{titre}</h1>
      </td></tr>
      <tr><td align="center" style="padding:14px 34px 0 34px;">
        <p style="margin:0;font-size:15.5px;line-height:1.62;color:#55554C;">{texte}</p>
      </td></tr>
      <tr><td align="center" style="padding:28px 32px 0 32px;">
        <table role="presentation" cellpadding="0" cellspacing="0" border="0">
          <tr><td align="center" style="border-radius:9px;background:{encre};">
            <a href="{{{{ .ConfirmationURL }}}}"
               style="display:inline-block;padding:15px 38px;font-size:16px;font-weight:700;
                      color:{jaune};text-decoration:none;border-radius:9px;">{bouton}</a>
          </td></tr>
        </table>
      </td></tr>
      <tr><td align="center" style="padding:22px 34px 0 34px;">
        <p style="margin:0;font-size:13px;line-height:1.6;color:#8A8A7E;">
          Le bouton ne fonctionne pas ? Copiez ce lien dans votre navigateur :</p>
        <p style="margin:8px 0 0 0;font-size:12px;line-height:1.55;word-break:break-all;">
          <a href="{{{{ .ConfirmationURL }}}}" style="color:#55554C;">{{{{ .ConfirmationURL }}}}</a></p>
      </td></tr>
      <tr><td style="padding:26px 34px 0 34px;">
        <div style="height:1px;background:#E2E2DA;font-size:0;line-height:0;">&nbsp;</div>
      </td></tr>
      <tr><td align="center" style="padding:20px 34px 32px 34px;">
        <p style="margin:0;font-size:12.5px;line-height:1.65;color:#9A9A8E;">{pied}</p>
      </td></tr>
    </table>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:520px;">
      <tr><td align="center" style="padding:18px 20px 0 20px;">
        <p style="margin:0;font-size:11.5px;line-height:1.6;color:#A5A59A;">
          Alluxe — message automatique, merci de ne pas y répondre.</p>
      </td></tr>
    </table>
  </td></tr>
</table>
"""

IGNORER = ("Si vous n'êtes pas à l'origine de cette demande, ignorez ce "
           "message : rien ne sera modifié.")

COURRIELS = {
    "confirmation": dict(
        cle="confirmation",
        sujet="Confirmez votre adresse — Alluxe",
        titre="Confirmez votre adresse",
        texte=("Bienvenue. Il reste une étape : confirmez que cette adresse "
               "est bien la vôtre, et votre compte sera actif."),
        bouton="Confirmer mon adresse",
        pied="Ce lien expire dans 24 heures.<br>Si vous n'êtes pas à "
             "l'origine de cette inscription, ignorez ce message : aucun "
             "compte ne sera créé."),
    "recovery": dict(
        cle="recovery",
        sujet="Réinitialiser votre mot de passe — Alluxe",
        titre="Nouveau mot de passe",
        texte=("Vous avez demandé à changer votre mot de passe. Ce lien vous "
               "mènera directement à la page où le choisir."),
        bouton="Choisir un mot de passe",
        pied=f"Ce lien expire dans 1 heure.<br>{IGNORER} Votre mot de passe "
             "actuel reste valable."),
    "magic_link": dict(
        cle="magic_link",
        sujet="Votre lien de connexion — Alluxe",
        titre="Connectez-vous",
        texte=("Voici votre lien de connexion. Un seul clic, sans mot de "
               "passe à retenir."),
        bouton="Me connecter",
        pied=f"Ce lien expire dans 1 heure et ne fonctionne qu'une fois.<br>{IGNORER}"),
    "email_change": dict(
        cle="email_change",
        sujet="Confirmez votre nouvelle adresse — Alluxe",
        titre="Votre nouvelle adresse",
        texte=("Vous avez demandé à changer l'adresse de votre compte. "
               "Confirmez la nouvelle pour qu'elle prenne effet."),
        bouton="Confirmer le changement",
        pied=f"Ce lien expire dans 24 heures.<br>{IGNORER} L'ancienne "
             "adresse restera celle de votre compte."),
    "invite": dict(
        cle="invite",
        sujet="Vous êtes invité sur Alluxe",
        titre="Vous êtes invité",
        texte=("Quelqu'un vous a invité à rejoindre Alluxe. Acceptez "
               "l'invitation pour créer votre compte."),
        bouton="Rejoindre Alluxe",
        pied="Ce lien expire dans 24 heures.<br>Si cette invitation ne vous "
             "était pas destinée, ignorez ce message."),
}


def rendre(c: dict) -> str:
    return GABARIT.format(logo=LOGO, aplat=JAUNE_APLAT, jaune=JAUNE_PUR,
                          encre=ENCRE, titre=c["titre"], texte=c["texte"],
                          bouton=c["bouton"], pied=c["pied"])


def main() -> int:
    dossier = Path(__file__).parent
    reglages = {}
    for nom, c in COURRIELS.items():
        html = rendre(c)
        (dossier / f"{nom}.html").write_text(html, encoding="utf-8")
        reglages[f"mailer_subjects_{c['cle']}"] = c["sujet"]
        reglages[f"mailer_templates_{c['cle']}_content"] = html
        print(f"  {nom + '.html':<24} {len(html):>5} caracteres")

    if "--publier" not in sys.argv:
        print("\n(fichiers ecrits — relancer avec --publier pour les installer)")
        return 0

    jeton = os.environ["SUPABASE_ACCESS_TOKEN"]
    ref = os.environ["SUPABASE_URL"].split("//")[1].split(".")[0]
    req = urllib.request.Request(
        f"https://api.supabase.com/v1/projects/{ref}/config/auth",
        data=json.dumps(reglages).encode(), method="PATCH",
        headers={"Authorization": f"Bearer {jeton}",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            conf = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code} : {e.read().decode()[:300]}", file=sys.stderr)
        return 1

    print("\n  installes :")
    for nom, c in COURRIELS.items():
        corps = conf.get(f"mailer_templates_{c['cle']}_content") or ""
        ok = "marque/logo.png" in corps and "ConfirmationURL" in corps
        print(f"    {nom:<16} {'OK' if ok else 'ABSENT'}   "
              f"{conf.get(f'mailer_subjects_{c[chr(39)+chr(39)] if False else chr(39)}', '') if False else conf.get('mailer_subjects_' + c['cle'], '')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
