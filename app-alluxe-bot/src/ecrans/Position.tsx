/**
 * Le detail d'une position -- le meme ecran pour le reel et pour la demo.
 *
 * Demande de l'operateur le 19 sept. : « quand je clique sur la position
 * ouverte je veux une page avec les infos de la position, a quel niveau
 * ouvert, a quelle heure, la quantite de lot, le stop loss d'ouverture et
 * l'actuel s'il a monte, un graphique de la crypto en 1m 5m 15m 30m 1h 4h
 * 1 jour, le benef ou negatif actuel, le pourcentage ».
 *
 * UN SEUL ECRAN POUR LES DEUX MODES. Il recoit la position et le capital
 * en parametres de navigation : rien ici ne sait s'il s'agit du reel ou
 * de la simulation, donc rien ne peut diverger entre les deux.
 */
import React from "react";
import { ScrollView, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Pressable } from "react-native";
import { Position } from "../services/robot";
import { Bougie, UNITES, Unite, bougies } from "../services/bougies";
import { usePrixLive } from "../services/prixLive";
import { chiffresDe } from "../composants/positionsTri";
import { euros, nomCrypto, pourcent, prix as fmtPrix, quand }
  from "../services/format";
import { espace, rayon } from "../theme";
import { Carte, Chargement, T, useCouleurs } from "../composants/base";
import { Graphique, NiveauTrace } from "../composants/Graphique";

export interface ParamsPosition {
  position: Position;
  /** Capital du mode d'ou l'on vient. Sert de repli quand la ligne n'a
   *  pas son propre `capital_eur` (publications d'avant le 19 sept.). */
  capital: number;
  /** "Réel" ou "Démo" : affiche d'ou vient la position, sans rien
   *  changer au calcul. */
  mode: string;
}

/** Une ligne « libelle -> valeur », l'unite de base de cet ecran. */
function Ligne({ libelle, valeur, couleur, aide }: {
  libelle: string; valeur: string; couleur?: string; aide?: string;
}) {
  const c = useCouleurs();
  return (
    <View style={{ flexDirection: "row", justifyContent: "space-between",
                   alignItems: "flex-start", paddingVertical: espace.s,
                   gap: espace.m }}>
      <View style={{ flexShrink: 1 }}>
        <T v="corps" couleur={c.encreDouce}>{libelle}</T>
        {!!aide && (
          <T v="legende" couleur={c.encrePale} style={{ marginTop: 2 }}>{aide}</T>
        )}
      </View>
      <T v="chiffre" couleur={couleur}>{valeur}</T>
    </View>
  );
}

function ChoixUnite({ unite, surChoix }: {
  unite: Unite; surChoix: (u: Unite) => void;
}) {
  const c = useCouleurs();
  return (
    <View style={{ flexDirection: "row", flexWrap: "wrap", gap: espace.xs,
                   marginBottom: espace.s }}>
      {UNITES.map(({ cle, libelle }) => {
        const actif = cle === unite;
        return (
          <Pressable
            key={cle}
            onPress={() => surChoix(cle)}
            accessibilityRole="button"
            accessibilityLabel={`Graphique en ${libelle}`}
            style={{
              paddingVertical: 6, paddingHorizontal: espace.m,
              borderRadius: rayon.rond,
              backgroundColor: actif ? c.jauneAplat : c.creux,
            }}
          >
            <T v="petit" couleur={actif ? c.surJaune : c.encreDouce}>{libelle}</T>
          </Pressable>
        );
      })}
    </View>
  );
}

/**
 * `route` est type large : le navigateur ne connait pas nos parametres
 * (la pile n'est pas typee dans ce projet), et lui imposer une signature
 * stricte ferait echouer la compilation a la declaration de l'ecran.
 * Le contrat reel est `ParamsPosition`, et les deux seuls appelants --
 * Direct et Demo -- le respectent.
 */
export function EcranPosition({ route }: any) {
  const c = useCouleurs();
  const marges = useSafeAreaInsets();
  const { position: p, capital, mode } = route.params as ParamsPosition;

  const [unite, setUnite] = React.useState<Unite>("1h");
  const [barres, setBarres] = React.useState<Bougie[] | null>(null);

  // La cotation en direct, meme source et meme rythme que les listes --
  // un seul appel rend tous les marches, donc suivre une position ne
  // coute pas moins cher que de les suivre toutes.
  const prixLive = usePrixLive(true);
  const prixActuel = prixLive[p.pair];

  React.useEffect(() => {
    let vivant = true;
    setBarres(null);
    bougies(p.pair, unite).then((b) => { if (vivant) setBarres(b); });
    return () => { vivant = false; };
  }, [p.pair, unite]);

  const ch = chiffresDe(p, capital, prixActuel);
  const stopCourant = p.stop_loss_actuel ?? p.stop_loss;
  const stopABouge = p.stop_loss_actuel != null
    && Math.abs(p.stop_loss_actuel - p.stop_loss) > 1e-12;
  const aLAbri = p.side === "sell"
    ? stopCourant < p.entry_price
    : stopCourant > p.entry_price;

  const niveaux: NiveauTrace[] = React.useMemo(() => {
    const n: NiveauTrace[] = [
      { prix: p.entry_price, libelle: "Achat", couleur: c.encreDouce },
      { prix: stopCourant, libelle: "Stop", couleur: aLAbri ? c.gain : c.perte },
    ];
    // Le stop d'origine n'apparait que s'il a bouge : sinon il ferait
    // doublon avec la ligne ci-dessus, deux traits exactement superposes.
    if (stopABouge) {
      n.push({ prix: p.stop_loss, libelle: "Stop d'origine",
               couleur: c.encrePale, pointille: true });
    }
    if (p.take_profit_1) {
      n.push({ prix: p.take_profit_1, libelle: "Objectif",
               couleur: c.olive, pointille: true });
    }
    return n;
  }, [p, stopCourant, stopABouge, aLAbri, c]);

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: c.fond }}
      contentContainerStyle={{ paddingTop: marges.top + espace.xxl,
                               paddingHorizontal: espace.l,
                               paddingBottom: espace.xxl }}
    >
      <View style={{ flexDirection: "row", alignItems: "center",
                     gap: espace.s, marginBottom: espace.xs }}>
        <T v="titreGrand">{nomCrypto(p.pair)}</T>
        <View style={{ paddingHorizontal: espace.s, paddingVertical: 2,
                       borderRadius: rayon.rond, backgroundColor: c.creux }}>
          <T v="legende" couleur={c.encreDouce}>{mode}</T>
        </View>
      </View>
      <T v="petit" couleur={c.encreDouce} style={{ marginBottom: espace.l }}>
        {p.pair} · {p.side === "buy" ? "Achat" : "Vente"} · étage{" "}
        {ch?.etage ?? 1}
      </T>

      {/* --- Le resultat, en gros : c'est ce qu'il vient voir --- */}
      <Carte accent style={{ marginBottom: espace.l, alignItems: "center" }}>
        <T v="petit" couleur={c.encreDouce}>Résultat en direct</T>
        {ch == null ? <Chargement /> : (
          <>
            <T v="titreGrand" couleur={ch.eur >= 0 ? c.gain : c.perte}
               style={{ marginTop: espace.xs }}>
              {euros(ch.eur)}
            </T>
            <T v="corps" couleur={ch.eur >= 0 ? c.gain : c.perte}>
              {pourcent(ch.pctPrix)}
            </T>
          </>
        )}
        {aLAbri && (
          <T v="petit" couleur={c.gain} style={{ marginTop: espace.s }}>
            À l'abri — le stop est au-dessus du prix d'achat
          </T>
        )}
      </Carte>

      {/* --- Le graphique --- */}
      <T v="sousTitre" style={{ marginBottom: espace.s }}>Graphique</T>
      <ChoixUnite unite={unite} surChoix={setUnite} />
      {barres == null ? (
        <View style={{ height: 300, alignItems: "center",
                       justifyContent: "center" }}>
          <Chargement />
        </View>
      ) : (
        <Graphique bougies={barres} niveaux={niveaux} hauteur={300} />
      )}

      {/* --- Les chiffres de la position --- */}
      <T v="sousTitre" style={{ marginTop: espace.xl, marginBottom: espace.xs }}>
        La position
      </T>
      <Carte>
        <Ligne libelle="Prix d'achat" valeur={fmtPrix(p.entry_price)} />
        <Ligne libelle="Prix actuel"
               valeur={prixActuel != null ? fmtPrix(prixActuel) : "—"} />
        {/* EN EUROS, TOUJOURS. « 7 489 777 unités de PEPE » ne dit rien a
            personne ; « 25,02 € » se comprend sans effort. Consigne de
            l'operateur, deja notee pour les ATR et les R : on ne lui
            montre jamais une grandeur qu'il devrait convertir lui-meme.
            La quantite reste affichee en petit, parce qu'il l'a demandee
            -- mais c'est l'euro qui porte le chiffre. */}
        <Ligne libelle="Somme misée"
               valeur={ch != null && ch.mise > 0 ? euros(ch.mise) : "—"}
               aide={p.volume != null
                 ? `${p.volume.toLocaleString("fr-FR", { maximumFractionDigits: 8 })} ${p.pair.split("/")[0]}`
                 : undefined} />
        <Ligne libelle="Vaut aujourd'hui"
               valeur={p.volume != null && prixActuel != null
                 ? euros(p.volume * prixActuel) : "—"}
               couleur={ch != null && ch.eur >= 0 ? c.gain : c.perte} />
        <Ligne libelle="Ouverte" valeur={quand(p.published_at)} />
      </Carte>

      {/* --- La protection --- */}
      <T v="sousTitre" style={{ marginTop: espace.xl, marginBottom: espace.xs }}>
        La protection
      </T>
      <Carte>
        <Ligne libelle="Stop à l'ouverture" valeur={fmtPrix(p.stop_loss)} />
        <Ligne
          libelle="Stop actuel"
          valeur={fmtPrix(stopCourant)}
          couleur={aLAbri ? c.gain : undefined}
          aide={stopABouge
            ? "le stop suiveur a remonté la protection"
            : "pas encore remonté — le suiveur s'arme plus haut"}
        />
        {!!p.take_profit_1 && (
          <Ligne libelle="Objectif" valeur={fmtPrix(p.take_profit_1)} />
        )}
        {/* « AU PIRE −17,52 € » SUR UNE POSITION QUI NE PEUT PLUS PERDRE.
            Releve par l'operateur le 22 septembre sur le BTC de la
            demo 2 : achat a 70 421, stop remonte a 70 993 — donc AU-DESSUS
            du prix d'achat. Si ce stop saute, la position rend +3 €, pas
            −17,52. Le chiffre affiche etait celui du stop D'ORIGINE, que
            le suiveur avait remplace depuis longtemps.

            Ce n'est pas un detail d'affichage : c'est ce chiffre qui lui
            a fait croire que le robot risquait encore de l'argent sur
            cette ligne, et la conversation est partie de la. Une fois la
            position a l'abri, la seule phrase vraie est ce qu'elle
            GARANTIT. */}
        {aLAbri && p.volume != null ? (
          <Ligne
            libelle="Au pire"
            valeur={euros(p.volume * (p.side === "sell"
              ? p.entry_price - stopCourant
              : stopCourant - p.entry_price))}
            couleur={c.gain}
            aide="le stop est au-dessus du prix d'achat : c'est un gain garanti"
          />
        ) : (
          <Ligne
            libelle="Au pire"
            valeur={ch != null
              ? euros(-Math.abs((p.capital_eur ?? capital)
                  * ((p.position_size_pct ?? 0) / 100)))
              : "—"}
            couleur={c.perte}
            aide="ce que coûterait le stop d'origine"
          />
        )}
      </Carte>

      <T v="legende" couleur={c.encrePale}
         style={{ marginTop: espace.l, textAlign: "center" }}>
        Graphique tracé sur les cotations Bitvavo — la même source que
        celle qui sert au robot pour décider.
      </T>
    </ScrollView>
  );
}
