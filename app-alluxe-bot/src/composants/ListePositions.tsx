/**
 * La liste des positions ouvertes -- UNE SEULE, pour le reel ET la demo.
 *
 * POURQUOI CE FICHIER EXISTE.
 *
 * Demande de l'operateur le 19 sept. : « tu fais le mode demo et reel
 * identiques, à chaque fois si je fais une modif sur l'un ça la fait sur
 * l'autre ». La seule facon de le GARANTIR est qu'il n'y ait qu'un seul
 * code -- pas deux fichiers a tenir d'accord.
 *
 * Avant ce fichier, `Direct.tsx` et `Demo.tsx` portaient chacun leur
 * copie de la ligne de position, identiques au commentaire pres. Deux
 * copies finissent toujours par diverger : c'est la lecon que ce depot
 * paie depuis le debut (voir CLAUDE.md, « deux endroits decidaient du
 * meme reglage »). Ici la divergence devient impossible.
 *
 * Ce qui differe legitimement entre les deux ecrans (le titre, le
 * capital affiche, l'historique) reste dans chaque ecran. Ce qui doit
 * etre identique vit ici.
 */
import React from "react";
import { Pressable, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import type { Position } from "../services/robot";
import { euros, nomCrypto, pourcent } from "../services/format";
import { Chiffres, TRIS, Tri, chiffresDe, trier } from "./positionsTri";

// Reexportes pour que les ecrans n'aient qu'un seul import a faire.
export { TRIS, chiffresDe, trier } from "./positionsTri";
export type { Chiffres, Tri } from "./positionsTri";
import { espace, rayon } from "../theme";
import { T, useCouleurs } from "./base";

// ---------------------------------------------------------------------
//  Le tri
// ---------------------------------------------------------------------

/**
 * La barre de tri. Toucher le critere actif inverse le sens -- c'est ce
 * qu'attend l'operateur (« de la plus grosse a la plus petite ») sans
 * avoir a chercher un second bouton.
 */
export function BarreDeTri({ tri, descendant, surChangement }: {
  tri: Tri; descendant: boolean;
  surChangement: (tri: Tri, descendant: boolean) => void;
}) {
  const c = useCouleurs();
  return (
    <View style={{ flexDirection: "row", flexWrap: "wrap", gap: espace.s,
                   marginBottom: espace.s }}>
      {TRIS.map(({ cle, libelle }) => {
        const actif = cle === tri;
        return (
          <Pressable
            key={cle}
            onPress={() => surChangement(cle, actif ? !descendant : true)}
            accessibilityRole="button"
            accessibilityLabel={`Trier par ${libelle}`}
            style={{
              flexDirection: "row", alignItems: "center", gap: 4,
              paddingVertical: 6, paddingHorizontal: espace.m,
              borderRadius: rayon.rond,
              backgroundColor: actif ? c.jauneAplat : c.creux,
            }}
          >
            <T v="petit" couleur={actif ? c.surJaune : c.encreDouce}>{libelle}</T>
            {actif && (
              <Ionicons name={descendant ? "arrow-down" : "arrow-up"}
                        size={12} color={c.surJaune} />
            )}
          </Pressable>
        );
      })}
    </View>
  );
}

// ---------------------------------------------------------------------
//  La ligne
// ---------------------------------------------------------------------

export function LignePosition({ p, capital, prixActuel, surAppui }: {
  p: Position; capital: number; prixActuel: number | undefined;
  surAppui?: () => void;
}) {
  const c = useCouleurs();
  const ch = chiffresDe(p, capital, prixActuel);

  const cadre = {
    flexDirection: "row" as const, justifyContent: "space-between" as const,
    alignItems: "center" as const,
    backgroundColor: c.surface, borderRadius: rayon.l,
    paddingVertical: espace.m, paddingHorizontal: espace.l,
    marginBottom: espace.s,
  };

  if (ch == null) {
    return (
      <View style={cadre}>
        <T v="sousTitre">{nomCrypto(p.pair)}</T>
        <T v="petit" couleur={c.encreDouce}>cotation...</T>
      </View>
    );
  }

  const couleur = ch.eur >= 0 ? c.gain : c.perte;
  // Le stop est-il passe au-dessus du prix d'achat ? Alors la position
  // ne peut plus rien perdre. C'est l'information la plus rassurante de
  // l'ecran, et elle n'apparaissait nulle part.
  const stopCourant = p.stop_loss_actuel ?? p.stop_loss;
  const aLAbri = p.side === "sell"
    ? stopCourant < p.entry_price
    : stopCourant > p.entry_price;

  return (
    <Pressable
      onPress={surAppui}
      accessibilityRole={surAppui ? "button" : undefined}
      accessibilityLabel={`${nomCrypto(p.pair)}, voir le détail`}
      style={({ pressed }) => [cadre, pressed && surAppui ? { opacity: 0.6 } : null]}
    >
      <View style={{ flex: 1 }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
          <T v="sousTitre">{nomCrypto(p.pair)}</T>
          {aLAbri && (
            <Ionicons name="shield-checkmark" size={13} color={c.gain} />
          )}
        </View>
        <T v="petit" couleur={c.encreDouce}>
          {p.side === "buy" ? "Achat" : "Vente"}
        </T>
        <View style={{ flexDirection: "row", alignItems: "center",
                       marginTop: espace.xs }}>
          <T v="petit" couleur={c.encreDouce}>
            {ch.mise > 0 ? `${euros(ch.mise)} misés` : "mise inconnue"}
          </T>
          {/* L'etage s'affiche TOUJOURS, meme au premier : sinon
              l'information n'est jamais visible tant que le pyramidage
              ne s'est pas declenche. Demande explicite de l'operateur. */}
          <T v="petit" couleur={ch.etage > 1 ? c.olive : c.encreDouce}>
            {" · étage " + ch.etage}
          </T>
        </View>
      </View>
      <View style={{ alignItems: "flex-end" }}>
        <T v="chiffre" couleur={couleur}>{euros(ch.eur)}</T>
        <T v="petit" couleur={couleur}>{pourcent(ch.pctPrix)}</T>
      </View>
      {!!surAppui && (
        <Ionicons name="chevron-forward" size={18} color={c.encrePale}
                  style={{ marginLeft: espace.s }} />
      )}
    </Pressable>
  );
}
