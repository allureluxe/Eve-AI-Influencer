# Mode d'emploi — de la clé API au robot qui tourne

Tout est dans **un seul script**. Il vérifie à chaque étape et s'arrête au
premier problème en disant quoi faire.

```bash
cd ~/Eve-AI-Influencer && bash finaliser.sh
```

---

## Avant de le lancer : mettre la clé dans `.env`

```bash
nano ~/Eve-AI-Influencer/.env
```

Ajoute à la fin :

```
BITVAVO_API_KEY=ta_cle
BITVAVO_API_SECRET=ton_secret
BITVAVO_DRY_RUN=1
GB_CONFIG=robot.bitvavo.json
```

`Ctrl+O`, `Entrée`, `Ctrl+X` pour enregistrer.

**Laisse `BITVAVO_DRY_RUN=1`.** C'est le verrou qui empêche tout ordre réel.

Pour relire le fichier sans afficher les valeurs :

```bash
sed 's/=.*/=********/' ~/Eve-AI-Influencer/.env
```

---

## Ce que fait `finaliser.sh`

| Étape | Vérifie |
|---|---|
| 1 | le code est à jour |
| 2 | les 442 tests passent |
| 3 | les clés sont présentes (longueur seulement, jamais la valeur) |
| 4 | la connexion Bitvavo, le solde, le tarif réel, le calibrage |
| 5 | un balayage réel des 85 cryptos |
| 6 | affiche les commandes du service |

Il **ne passe jamais en argent réel tout seul**.

---

## Mettre le robot en service

```bash
sudo bash service.sh installer
sudo bash service.sh demarrer
bash service.sh journal          # suivre en direct, Ctrl+C pour sortir
```

Autres commandes : `arreter`, `etat`, `desinstaller`.

Il redémarre seul après un reboot ou une coupure réseau.

---

## Si ça coince

| Message | Cause | Solution |
|---|---|---|
| `fichier .env absent` | pas encore créé | `cp .env.example .env` puis `nano .env` |
| `manquant dans .env` | clés non collées | `nano .env` |
| `connexion refusee` | clé, IP, horloge ou droit | voir les 4 causes affichées |
| `capital insuffisant` | ticket minimum hors de portée | le calibrage affiche le capital requis |
| `231 tests / OK` | pytest absent | `sudo apt-get install -y python3-pytest` |
| `Please ask your administrator` | PEP 668 | passer par `apt`, pas `pip3` |

**IP du serveur à autoriser sur la clé** : `92.222.90.65`

---

## Passer en argent réel — quand TU l'auras décidé

1. `nano .env` → mettre `BITVAVO_DRY_RUN=0`
2. `python3 verifier_bitvavo.py --confirmer`
   Un aller-retour réel d'environ 10 €, coût ~0,05 €, visible dans ton
   historique Bitvavo. C'est la preuve que l'exécution fonctionne.
3. `sudo bash service.sh demarrer`

Pour revenir en arrière à tout moment : `BITVAVO_DRY_RUN=1` puis
`sudo bash service.sh redemarrer`.

---

## Ce que tu dois savoir avant de le faire

**Le backtest en est à 16 trades sur deux mois.** C'est trop peu pour
affirmer que la stratégie gagne. Ce qui est prouvé, c'est que la chaîne est
saine et que la mesure est juste — pas que le résultat est bon.

**Sur Bitvavo, seule l'unité D1 est praticable**, quel que soit ton capital.
À 0,25 % de frais par côté, il faut des stops d'au moins 3,3 % du prix, et
aucune unité entre H4 (3,08 %) et D1 (6 %) ne rentre. Ajouter du capital n'y
change rien : le mur est dans le tarif.

Concrètement : **quelques positions par semaine, tenues plusieurs jours.**
Pas du scalping. Le H1 n'existe que sur OKX, dont les frais sont 2,5 fois
plus bas — le connecteur est écrit et testé, il n'attend qu'une clé.

**La simulation n'est pas du temps perdu.** La pondération adaptative démarre
neutre et n'apprend qu'avec des trades fermés. Quelques jours en simulation
lui donnent de quoi commencer à distinguer ce qui marche.

---

## Les garde-fous en place

- stop-loss obligatoire, refus d'ouvrir sans lui
- mise progressive/régressive selon le capital (×1,80 à +50 %, ×0,35 à −25 %)
- réduction après pertes consécutives et pendant un drawdown
- coupe-circuits : perte journalière, hebdomadaire, drawdown maximal
- plafond de coût : tout trade dont les frais dépassent 15 % du risque est refusé
- la clé n'a pas le droit de retrait — même compromise, elle ne peut pas vider le compte
