/**
 * Onglet Luna -- le personnage, et la file de generation de contenu.
 *
 * PREMIERE VERSION (16 sept.) : affiche le personnage (luna/persona.py,
 * republie par ops/executer_luna.py) et l'historique des generations
 * demandees, avec la photo quand elle existe. Volontairement SANS
 * lecteur audio/video integre pour l'instant -- ca demanderait
 * expo-av, une dependance native de plus, pour un premier passage dont
 * le but est de rendre la file utilisable (voir ce qui a ete genere,
 * en demander une nouvelle). Meme discipline que Discussion.tsx :
 * livrer un morceau vrai et utile plutot qu'une promesse complete.
 *
 * Generer un post prend du temps reel (LLM + image + voix + video, sur
 * le VPS, via cron toutes les 2 min) -- l'ecran ne bloque jamais en
 * l'attendant, il rafraichit la liste toutes les 15 s comme Alertes.tsx.
 */
import React from "react";
import { Image, RefreshControl, ScrollView, TextInput, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import {
  Publication, Persona, StatutPublication,
  demanderGeneration, persona as chargerPersona, publications, urlSignee,
} from "../services/luna";
import { espace, rayon, TRAIT } from "../theme";
import { Bouton, Carte, Chargement, Logo, T, useCouleurs, Vide } from "../composants/base";

const RYTHME_MS = 15_000;

const LIBELLE_STATUT: Record<StatutPublication, string> = {
  en_attente: "En attente",
  en_cours: "En cours de generation",
  terminee: "Terminee",
  echec: "Echouee",
};

function couleurStatut(c: ReturnType<typeof useCouleurs>, s: StatutPublication): string {
  if (s === "terminee") return c.gain;
  if (s === "echec") return c.perte;
  if (s === "en_cours") return c.vigilance;
  return c.encrePale;
}

function CartePersona({ p }: { p: Persona }) {
  const c = useCouleurs();
  return (
    <Carte accent style={{ marginBottom: espace.l }}>
      <T v="titre">{p.prenom}, {p.age} ans</T>
      <T v="petit" couleur={c.encreDouce} style={{ marginTop: 2 }}>{p.metier}</T>
      {!!p.contexte && (
        <T v="corps" style={{ marginTop: espace.m }}>{p.contexte}</T>
      )}
      {p.caractere.length > 0 && (
        <View style={{ marginTop: espace.m }}>
          {p.caractere.map((trait, i) => (
            <T key={i} v="petit" couleur={c.encreDouce} style={{ marginTop: i ? 2 : 0 }}>
              • {trait}
            </T>
          ))}
        </View>
      )}
    </Carte>
  );
}

function PhotoPublication({ chemin }: { chemin: string }) {
  const c = useCouleurs();
  const [url, setUrl] = React.useState<string | null>(null);
  React.useEffect(() => {
    let vivant = true;
    urlSignee(chemin).then((u) => { if (vivant) setUrl(u); });
    return () => { vivant = false; };
  }, [chemin]);

  if (!url) {
    return (
      <View style={{ width: "100%", aspectRatio: 1, borderRadius: rayon.m,
                     backgroundColor: c.creux, marginTop: espace.m }} />
    );
  }
  return (
    <Image source={{ uri: url }} style={{
      width: "100%", aspectRatio: 1, borderRadius: rayon.m, marginTop: espace.m,
    }} />
  );
}

function CartePublication({ pub }: { pub: Publication }) {
  const c = useCouleurs();
  const quand = new Date(pub.created_at).toLocaleString("fr-FR", {
    day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
  });
  return (
    <Carte style={{ marginBottom: espace.m }}>
      <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" }}>
        <T v="petit" couleur={c.encreDouce} style={{ flex: 1, marginRight: espace.s }}>
          {pub.demande || "(Luna improvise)"}
        </T>
        <T v="legende">{quand}</T>
      </View>
      <T v="sousTitre" couleur={couleurStatut(c, pub.statut)} style={{ marginTop: 4 }}>
        {LIBELLE_STATUT[pub.statut]}
      </T>
      {!!pub.legende && <T v="corps" style={{ marginTop: espace.s }}>{pub.legende}</T>}
      {pub.chemin_photo && <PhotoPublication chemin={pub.chemin_photo} />}
      {pub.chemin_voix && (
        <T v="legende" style={{ marginTop: espace.s }}>🔊 voix generee (lecture dans l'app : bientot)</T>
      )}
      {pub.chemin_video && (
        <T v="legende" style={{ marginTop: 2 }}>🎬 video generee (lecture dans l'app : bientot)</T>
      )}
      {Object.keys(pub.erreurs ?? {}).length > 0 && (
        <View style={{ marginTop: espace.s }}>
          {Object.entries(pub.erreurs).map(([etape, msg]) => (
            <T key={etape} v="legende" couleur={c.perte}>! {etape} : {msg}</T>
          ))}
        </View>
      )}
    </Carte>
  );
}

export function EcranLuna() {
  const c = useCouleurs();
  const marges = useSafeAreaInsets();
  const [p, setP] = React.useState<Persona | null>(null);
  const [liste, setListe] = React.useState<Publication[] | null>(null);
  const [demande, setDemande] = React.useState("");
  const [envoi, setEnvoi] = React.useState(false);
  const [rafraichit, setRafraichit] = React.useState(false);
  const [erreur, setErreur] = React.useState("");

  const charger = React.useCallback(async () => {
    try {
      const [pers, pubs] = await Promise.all([chargerPersona(), publications()]);
      setP(pers); setListe(pubs); setErreur("");
    } catch (err: any) {
      setErreur(err?.message ?? "Erreur de chargement");
    }
  }, []);

  React.useEffect(() => {
    charger();
    const id = setInterval(charger, RYTHME_MS);
    return () => clearInterval(id);
  }, [charger]);

  const surRafraichir = async () => {
    setRafraichit(true);
    await charger();
    setRafraichit(false);
  };

  const surGenerer = async () => {
    setEnvoi(true);
    try {
      await demanderGeneration(demande);
      setDemande("");
      await charger();
    } catch (err: any) {
      setErreur(err?.message ?? "Impossible d'envoyer la demande");
    } finally {
      setEnvoi(false);
    }
  };

  const enCours = (liste ?? []).some((pub) => pub.statut === "en_attente" || pub.statut === "en_cours");

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: c.fond }}
      contentContainerStyle={{ paddingTop: marges.top + espace.s,
                               paddingHorizontal: espace.l, paddingBottom: espace.xxl }}
      refreshControl={<RefreshControl refreshing={rafraichit} onRefresh={surRafraichir} />}
    >
      <View style={{ flexDirection: "row", alignItems: "center",
                     justifyContent: "space-between", marginBottom: espace.l }}>
        <T v="titreGrand">Luna</T>
        <Logo hauteur={40} />
      </View>

      {!!erreur && <T v="petit" couleur={c.perte} style={{ marginBottom: espace.m }}>{erreur}</T>}

      {p ? <CartePersona p={p} /> : <View style={{ marginBottom: espace.l }}><Chargement /></View>}

      <Carte style={{ marginBottom: espace.l }}>
        <T v="sousTitre">Nouveau post</T>
        <T v="petit" couleur={c.encreDouce} style={{ marginTop: 2, marginBottom: espace.m }}>
          Laisse vide pour que Luna improvise toute seule.
        </T>
        <TextInput
          value={demande}
          onChangeText={setDemande}
          placeholder="ex. un post sur son week-end au ski"
          placeholderTextColor={c.encrePale}
          multiline
          style={{
            borderWidth: TRAIT, borderColor: c.filet, borderRadius: rayon.s,
            padding: espace.m, minHeight: 60, color: c.encre,
            marginBottom: espace.m, textAlignVertical: "top",
          }}
        />
        <Bouton
          titre={enCours ? "Une generation est deja en cours..." : "Generer"}
          onPress={surGenerer}
          desactive={envoi || enCours}
        />
      </Carte>

      <T v="sousTitre" style={{ marginBottom: espace.m }}>Historique</T>
      {liste === null ? (
        <Chargement />
      ) : liste.length === 0 ? (
        <Vide titre="Aucun post genere pour l'instant" />
      ) : (
        liste.map((pub) => <CartePublication key={pub.id} pub={pub} />)
      )}
    </ScrollView>
  );
}
