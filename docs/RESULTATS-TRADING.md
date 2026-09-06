# Publier les résultats du système — chiffres réels uniquement

Eve peut parler du système de trading. Elle ne peut pas inventer un chiffre :
le générateur en est structurellement incapable.

## Comment ça marche

| Situation | Ce que produit l'agent |
|---|---|
| Pas de fichier de résultats | Contenu de **méthode** uniquement : ce qu'est un drawdown, pourquoi les robots vendus en ligne ne valent rien, comment on teste. Zéro chiffre. |
| Fichier présent et valide | Une publication sur deux cite les chiffres **du fichier**, avec période, drawdown et avertissement de risque. |
| Fichier présent mais incomplet | **Erreur, rien n'est produit.** Le message dit ce qui manque. |

C'est volontaire. Un chiffre ne peut pas apparaître dans une vidéo sans être
passé par ce fichier.

## Le fichier

Copie le modèle et remplis-le avec les chiffres réels :

```bash
mkdir -p data/trading
cp docs/exemples/trading-results.example.json data/trading/results.json
```

```json
{
  "system_name": "Nom de ton système",
  "account_currency": "EUR",
  "period": { "start": "2026-01-01", "end": "2026-07-31" },
  "verified_by": "Myfxbook",
  "verification_url": "https://www.myfxbook.com/…",
  "metrics": {
    "return_pct": 12.4,
    "max_drawdown_pct": 8.1,
    "trades": 412,
    "profit_factor": 1.32,
    "win_rate_pct": 54.2
  },
  "notes": "Compte réel, exécution automatique, aucun ajustement manuel."
}
```

## Les trois règles que le code fait respecter

**Le drawdown maximal est obligatoire.** Un rendement publié sans son risque
est trompeur même quand il est exact. Sans `max_drawdown_pct`, le chargement
échoue.

**La période doit être passée.** Une période qui se termine dans le futur est
refusée. On ne publie que du constaté.

**Un post chiffré porte toujours son cadre.** Le contrôle de conformité
(`eve/safety/policy.py`) rejette toute légende contenant un pourcentage de
performance sans drawdown *et* sans mention « résultats passés / pas un
conseil ». Ce n'est pas ajoutable après coup : la publication est bloquée.

## Ce qui reste interdit, données réelles ou pas

- Lier le train de vie d'Eve à un gain : elle est générée, elle n'a aucun revenu.
- Vendre, louer, faire copier ou recruter autour du système.
- Toute forme de « DM pour recevoir », « places limitées », « capital garanti ».

Ces règles sont dans le code (`LIFESTYLE_ATTRIBUTION_PATTERNS`,
`FINANCIAL_SOLICITATION_PATTERNS`) et couvertes par les tests.

## Vérification par un tiers

Si tu veux que ces chiffres aient du poids, relie un compte en lecture seule à
Myfxbook, FX Blue ou équivalent, et mets l'URL dans `verification_url`. Un
chiffre vérifié par un tiers vaut cent captures d'écran.
