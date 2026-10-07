/**
 * Onglet alluxe.ia — remplace Luna (décision de l'opérateur, 7 oct. 2026).
 *
 * Cinq sous-onglets : Bilan (chiffres du compte), Commenter (la liste du jour
 * préparée par l'assistant), À publier (les Reels prêts, à poster depuis le
 * téléphone pour garder la musique et le partage Facebook), Posts (chaque
 * publication et ses statistiques), TikTok.
 *
 * Rien ici ne publie ni ne commente : l'appli montre, l'opérateur agit.
 * Copier passe par la feuille de partage du téléphone (« Copier »), qui ne
 * demande aucun module natif — donc pas de nouvel APK (règle du 29 sept.).
 */
import React from "react";
import { Linking, Pressable, RefreshControl, ScrollView, Share, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";

import {
  APublier, Cible, CompteReseau, Media, aPublier, cibles, comptes, lienVideo, marquerCible, marquerPublie, medias,
} from "../services/alluxeIa";
import { espace, rayon, TRAIT } from "../theme";
import { Bouton, Carte, Logo, T, useCouleurs, Vide } from "../composants/base";

type Section = "bilan" | "commenter" | "publier" | "posts" | "tiktok";
const SECTIONS: [Section, string][] = [
  ["bilan", "Bilan"], ["commenter", "Commenter"], ["publier", "À publier"], ["posts", "Posts"], ["tiktok", "TikTok"],
];
const RYTHME_MS = 60_000;
const OBJECTIF_ABONNES = 1000;
const TIKTOK = "https://www.tiktok.com/@alluxe.ia";
const INSTAGRAM = "https://www.instagram.com/alluxe.ia/";

const nombre = (n: number | null | undefined) => (n == null ? "—" : n.toLocaleString("fr-FR"));
const jour = (iso: string | null) => iso ? new Date(iso).toLocaleDateString("fr-FR", { day: "numeric", month: "short" }) : "";
const copier = (texte: string) => Share.share({ message: texte });
const ouvrir = (url: string | null) => { if (url) Linking.openURL(url); };

function Onglets({ actif, surChoix, badges }: {
  actif: Section; surChoix: (s: Section) => void; badges: Partial<Record<Section, number>>;
}) {
  const c = useCouleurs();
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: espace.l }}
      contentContainerStyle={{ gap: espace.s }}>
      {SECTIONS.map(([cle, libelle]) => {
        const choisi = cle === actif;
        const n = badges[cle];
        return (
          <Pressable key={cle} onPress={() => surChoix(cle)} accessibilityRole="button"
            accessibilityState={{ selected: choisi }}
            style={{
              paddingVertical: espace.s, paddingHorizontal: espace.m, borderRadius: rayon.l,
              backgroundColor: choisi ? c.jauneAplat : c.surface, flexDirection: "row", alignItems: "center", gap: 6,
              borderWidth: choisi ? 0 : TRAIT, borderColor: c.filetDoux,
            }}>
            <T v="petit" couleur={choisi ? c.surJaune : c.encreDouce}>{libelle}</T>
            {!!n && (
              <View style={{ backgroundColor: c.encre, borderRadius: 999, paddingHorizontal: 6, minWidth: 18, alignItems: "center" }}>
                <T v="legende" couleur={c.fond}>{n}</T>
              </View>
            )}
          </Pressable>
        );
      })}
    </ScrollView>
  );
}

function Case({ valeur, libelle }: { valeur: string; libelle: string }) {
  const c = useCouleurs();
  return (
    <Carte style={{ flex: 1, minWidth: "45%" }}>
      <T v="titre">{valeur}</T>
      <T v="legende" couleur={c.encrePale}>{libelle}</T>
    </Carte>
  );
}

function Bilan({ ig, liste, nbCibles, nbAPublier, aller }: {
  ig: CompteReseau | undefined; liste: Media[]; nbCibles: number; nbAPublier: number; aller: (s: Section) => void;
}) {
  const c = useCouleurs();
  const reels = liste.filter((m) => m.type === "REEL");
  const meilleur = [...reels].sort((a, b) => (b.portee ?? 0) - (a.portee ?? 0))[0];
  const abonnes = ig?.abonnes ?? 0;
  return (
    <>
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: espace.s, marginBottom: espace.m }}>
        <Case valeur={nombre(ig?.abonnes)} libelle="abonnés Instagram" />
        <Case valeur={nombre(ig?.portee_7j)} libelle="comptes touchés, 7 jours" />
        <Case valeur={nombre(ig?.visites_profil_7j)} libelle="visites du profil, 7 jours" />
        <Case valeur={nombre(ig?.clics_site_7j)} libelle="clics vers alluxe.fr, 7 jours" />
      </View>

      <Carte style={{ marginBottom: espace.m }}>
        <T v="etiquette">Objectif {OBJECTIF_ABONNES.toLocaleString("fr-FR")} abonnés</T>
        <View style={{ height: 8, backgroundColor: c.creux, borderRadius: 999, overflow: "hidden", marginTop: espace.s }}>
          <View style={{ width: `${Math.min(100, (abonnes / OBJECTIF_ABONNES) * 100)}%`, height: 8, backgroundColor: c.jaune }} />
        </View>
        <T v="legende" style={{ marginTop: 4 }}>{abonnes} / {OBJECTIF_ABONNES} — le lien cliquable TikTok s'ouvre à 1 000.</T>
      </Carte>

      <Carte accent style={{ marginBottom: espace.m }}>
        <T v="etiquette">Aujourd'hui</T>
        <T v="corps" style={{ marginTop: 4 }}>
          {nbCibles > 0 ? `${nbCibles} post(s) à commenter (≈ 5 min).` : "Liste du jour faite ✓"}
          {nbAPublier > 0 ? `\n${nbAPublier} Reel(s) prêt(s) à publier.` : ""}
        </T>
        <View style={{ flexDirection: "row", gap: espace.s, marginTop: espace.s }}>
          {nbCibles > 0 && <Bouton titre="Commenter" onPress={() => aller("commenter")} />}
          {nbAPublier > 0 && <Bouton titre="À publier" variante="contour" onPress={() => aller("publier")} />}
        </View>
      </Carte>

      {meilleur && (
        <Pressable onPress={() => ouvrir(meilleur.lien)}>
          <Carte style={{ marginBottom: espace.m }}>
            <T v="etiquette">Meilleur Reel</T>
            <T v="corps" numberOfLines={2} style={{ marginTop: 4 }}>{(meilleur.legende ?? "").split("\n")[0]}</T>
            <T v="petit" style={{ marginTop: 4 }}>
              {nombre(meilleur.portee)} comptes touchés · {nombre(meilleur.vues)} vues · regardé {meilleur.duree_moyenne_s ?? "—"} s en moyenne
            </T>
          </Carte>
        </Pressable>
      )}
      <T v="legende">Mis à jour {ig ? new Date(ig.maj_le).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" }) : "—"} · toutes les 30 min</T>
    </>
  );
}

function CarteCible({ cible, surStatut }: { cible: Cible; surStatut: (s: Cible["statut"]) => void }) {
  const c = useCouleurs();
  const fini = cible.statut !== "a_faire";
  return (
    <Carte style={{ marginBottom: espace.m, opacity: fini ? 0.5 : 1 }}>
      <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
        <T v="etiquette">#{cible.hashtag} · {nombre(cible.likes)} ♥ · {nombre(cible.commentaires)} 💬</T>
        {fini && <T v="legende">{cible.statut === "fait" ? "fait ✓" : "ignoré"}</T>}
      </View>
      <T v="petit" numberOfLines={3} style={{ marginTop: 4 }}>{cible.legende}</T>
      <View style={{ backgroundColor: "#FDFFD0", borderRadius: rayon.m, padding: espace.m, marginTop: espace.s }}>
        <T v="corps" couleur="#15150F">{cible.commentaire_propose}</T>
      </View>
      {!fini && (
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: espace.s, marginTop: espace.s }}>
          <Bouton titre="Copier" onPress={() => copier(cible.commentaire_propose ?? "")} />
          <Bouton titre="Ouvrir le post" variante="contour" onPress={() => ouvrir(cible.lien)} />
          <Bouton titre="Fait ✓" variante="contour" onPress={() => surStatut("fait")} />
          <Bouton titre="Ignorer" variante="discret" onPress={() => surStatut("ignore")} />
        </View>
      )}
    </Carte>
  );
}

function CarteAPublier({ r, surPublie }: { r: APublier; surPublie: () => void }) {
  const c = useCouleurs();
  const [lien, setLien] = React.useState(false);
  const telecharger = async () => {
    if (!r.chemin_video) return;
    setLien(true);
    const url = await lienVideo(r.chemin_video);
    setLien(false);
    ouvrir(url);
  };
  const fini = r.statut === "publie";
  return (
    <Carte style={{ marginBottom: espace.m, opacity: fini ? 0.5 : 1 }}>
      <View style={{ flexDirection: "row", alignItems: "center", gap: espace.s }}>
        <Ionicons name={r.reseau === "tiktok" ? "logo-tiktok" : "logo-instagram"} size={18} color={c.encre} />
        <T v="sousTitre" style={{ flex: 1 }}>{r.titre}</T>
        {fini && <T v="legende">publié ✓</T>}
      </View>
      {!!r.musique && <T v="petit" style={{ marginTop: 4 }}>🎵 {r.musique}</T>}
      <T v="petit" numberOfLines={4} style={{ marginTop: 4 }}>{r.legende}</T>
      {!fini && (
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: espace.s, marginTop: espace.s }}>
          <Bouton titre={lien ? "…" : "Télécharger la vidéo"} onPress={telecharger} />
          <Bouton titre="Copier la légende" variante="contour" onPress={() => copier(r.legende ?? "")} />
          <Bouton titre="Publié ✓" variante="discret" onPress={surPublie} />
        </View>
      )}
    </Carte>
  );
}

function CarteMedia({ m }: { m: Media }) {
  const c = useCouleurs();
  const icone = m.type === "REEL" ? "film-outline" : m.type === "CARROUSEL" ? "albums-outline" : "image-outline";
  return (
    <Pressable onPress={() => ouvrir(m.lien)}>
      <Carte style={{ marginBottom: espace.s }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: espace.s }}>
          <Ionicons name={icone} size={16} color={c.encreDouce} />
          <T v="legende">{jour(m.publie_le)}</T>
          <T v="petit" numberOfLines={1} style={{ flex: 1 }}>{(m.legende ?? "").split("\n")[0]}</T>
        </View>
        <T v="chiffre" style={{ marginTop: 4, fontSize: 13 }}>
          👁 {nombre(m.portee)}  ▶ {nombre(m.vues)}  ♥ {nombre(m.likes)}  🔖 {nombre(m.enregistrements)}  ↗ {nombre(m.partages)}
          {m.type === "REEL" && m.duree_moyenne_s != null ? `  ⏱ ${m.duree_moyenne_s} s` : ""}
        </T>
      </Carte>
    </Pressable>
  );
}

export function EcranAlluxeIa() {
  const c = useCouleurs();
  const marges = useSafeAreaInsets();
  const [section, setSection] = React.useState<Section>("bilan");
  const [cpt, setCpt] = React.useState<CompteReseau[]>([]);
  const [liste, setListe] = React.useState<Media[]>([]);
  const [cib, setCib] = React.useState<Cible[]>([]);
  const [pub, setPub] = React.useState<APublier[]>([]);
  const [erreur, setErreur] = React.useState("");
  const [rafraichit, setRafraichit] = React.useState(false);

  const charger = React.useCallback(async () => {
    try {
      const [a, b, d, e] = await Promise.all([comptes(), medias(), cibles(), aPublier()]);
      setCpt(a); setListe(b); setCib(d); setPub(e); setErreur("");
    } catch (err: any) {
      setErreur(err?.message ?? "Erreur de chargement");
    }
  }, []);
  React.useEffect(() => {
    charger();
    const id = setInterval(charger, RYTHME_MS);
    return () => clearInterval(id);
  }, [charger]);

  const ig = cpt.find((x) => x.reseau === "instagram");
  const aFaire = cib.filter((x) => x.statut === "a_faire");
  const dernierJour = cib[0]?.jour;
  const ciblesDuJour = cib.filter((x) => x.jour === dernierJour);
  const pubAFaire = pub.filter((x) => x.statut === "a_publier");

  const statutCible = async (id: string, s: Cible["statut"]) => {
    setCib((l) => l.map((x) => (x.id === id ? { ...x, statut: s } : x)));
    try { await marquerCible(id, s); } catch (err: any) { setErreur(err?.message ?? "Échec"); charger(); }
  };
  const publie = async (id: string) => {
    setPub((l) => l.map((x) => (x.id === id ? { ...x, statut: "publie" } : x)));
    try { await marquerPublie(id, "publie"); } catch (err: any) { setErreur(err?.message ?? "Échec"); charger(); }
  };

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: c.fond }}
      contentContainerStyle={{ paddingTop: marges.top + espace.s, paddingHorizontal: espace.l, paddingBottom: espace.xxl }}
      refreshControl={<RefreshControl refreshing={rafraichit} onRefresh={async () => { setRafraichit(true); await charger(); setRafraichit(false); }} />}
    >
      <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: espace.l }}>
        <View>
          <T v="titreGrand">alluxe.ia</T>
          <T v="petit" couleur={c.encreDouce}>Instagram · TikTok · croissance</T>
        </View>
        <Logo hauteur={40} />
      </View>
      {!!erreur && <T v="petit" couleur={c.perte} style={{ marginBottom: espace.m }}>{erreur}</T>}

      <Onglets actif={section} surChoix={setSection} badges={{ commenter: aFaire.length, publier: pubAFaire.length }} />

      {section === "bilan" && (
        <Bilan ig={ig} liste={liste} nbCibles={aFaire.length} nbAPublier={pubAFaire.length} aller={setSection} />
      )}

      {section === "commenter" && (
        <>
          <Carte style={{ marginBottom: espace.m }}>
            <T v="petit">
              Chaque matin à 8 h : des posts IA francophones récents, avec un commentaire proposé.
              Ouvre le post, colle le commentaire (adapte-le si besoin), like. C'est toi qui publies :
              un robot qui commente fait masquer le compte par Instagram.
            </T>
          </Carte>
          {ciblesDuJour.length === 0 ? <Vide titre="Pas encore de liste" detail="Elle arrive chaque matin vers 8 h." /> :
            ciblesDuJour.map((x) => <CarteCible key={x.id} cible={x} surStatut={(s) => statutCible(x.id, s)} />)}
        </>
      )}

      {section === "publier" && (
        <>
          <Carte style={{ marginBottom: espace.m }}>
            <T v="petit">
              Les Reels préparés. Publie-les depuis ton téléphone : tu choisis la musique à l'oreille sur le
              passage fort, et Instagram partage tout seul sur ta page Facebook.
            </T>
          </Carte>
          {pub.length === 0 ? <Vide titre="Rien à publier" detail="Les prochains Reels apparaîtront ici." /> :
            pub.map((r) => <CarteAPublier key={r.id} r={r} surPublie={() => publie(r.id)} />)}
        </>
      )}

      {section === "posts" && (
        liste.length === 0 ? <Vide titre="Aucune publication" /> :
          liste.map((m) => <CarteMedia key={m.media_id} m={m} />)
      )}

      {section === "tiktok" && (
        <>
          <Carte style={{ marginBottom: espace.m }}>
            <T v="sousTitre">@alluxe.ia sur TikTok</T>
            <T v="petit" style={{ marginTop: 4 }}>
              Compte personnel : toute la musique de TikTok est disponible (les comptes entreprise n'ont que la
              bibliothèque libre). Les statistiques se lisent dans l'appli TikTok → Outils pour les créateurs.
            </T>
            <View style={{ flexDirection: "row", gap: espace.s, marginTop: espace.s }}>
              <Bouton titre="Ouvrir TikTok" onPress={() => ouvrir(TIKTOK)} />
              <Bouton titre="Ouvrir Instagram" variante="contour" onPress={() => ouvrir(INSTAGRAM)} />
            </View>
          </Carte>
          <T v="sousTitre" style={{ marginBottom: espace.s }}>À publier sur TikTok</T>
          {pub.filter((r) => r.reseau === "tiktok").length === 0 ? <Vide titre="Rien pour TikTok" /> :
            pub.filter((r) => r.reseau === "tiktok").map((r) => <CarteAPublier key={r.id} r={r} surPublie={() => publie(r.id)} />)}
        </>
      )}
    </ScrollView>
  );
}
