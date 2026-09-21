/**
 * Onglet Luna -- le personnage, et la file de generation de contenu.
 *
 * PREMIERE VERSION (16 sept.) : affiche le personnage (luna/persona.py,
 * republie par ops/executer_luna.py) et l'historique des generations
 * demandees, avec la photo quand elle existe. Meme discipline que
 * Discussion.tsx : livrer un morceau vrai et utile plutot qu'une
 * promesse complete.
 *
 * Lecture audio/video ajoutee dans un 2e passage (expo-av) : un simple
 * bouton lecture/pause pour la voix, un lecteur natif avec controles
 * pour la video -- pas de lecteur personnalise, `expo-av` fournit deja
 * les controles standard.
 *
 * Generer un post prend du temps reel (LLM + image + voix + video, sur
 * le VPS, via cron toutes les 2 min) -- l'ecran ne bloque jamais en
 * l'attendant, il rafraichit la liste toutes les 15 s comme Alertes.tsx.
 */
import React from "react";
import { Image, Pressable, RefreshControl, ScrollView, TextInput, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Audio, ResizeMode, Video } from "expo-av";
import { Ionicons } from "@expo/vector-icons";
import {
  Publication, Persona, StatutPublication,
  demanderGeneration, persona as chargerPersona, publications, urlSignee,
} from "../services/luna";
import { espace, rayon, TRAIT } from "../theme";
import { Bouton, Carte, Chargement, Logo, T, useCouleurs, Vide } from "../composants/base";
import { EtatReseaux, Reseau, etatReseaux } from "../services/reseaux";

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

/** « il y a 3 min », « hier » -- un horodatage lisible d'un coup d'oeil. */
function quandCourt(iso: string): string {
  const min = Math.max(0, (Date.now() - new Date(iso).getTime()) / 60000);
  if (min < 2) return "a l'instant";
  if (min < 60) return `il y a ${Math.round(min)} min`;
  if (min < 48 * 60) return `il y a ${Math.round(min / 60)} h`;
  return `il y a ${Math.round(min / 1440)} j`;
}

type Section = "reseaux" | "atelier" | "personnage";

const SECTIONS: { cle: Section; libelle: string }[] = [
  { cle: "reseaux", libelle: "Reseaux" },
  { cle: "atelier", libelle: "Atelier" },
  { cle: "personnage", libelle: "Luna" },
];

/** Le selecteur de section -- meme geste que la barre de tri des positions. */
function BarreSections({ actif, surChoix }: {
  actif: Section; surChoix: (s: Section) => void;
}) {
  const c = useCouleurs();
  return (
    <View style={{ flexDirection: "row", gap: espace.s, marginBottom: espace.l }}>
      {SECTIONS.map(({ cle, libelle }) => {
        const choisi = cle === actif;
        return (
          <Pressable
            key={cle}
            onPress={() => surChoix(cle)}
            accessibilityRole="button"
            accessibilityState={{ selected: choisi }}
            style={{
              flex: 1, paddingVertical: espace.s, borderRadius: rayon.l,
              alignItems: "center",
              backgroundColor: choisi ? c.jauneAplat : c.surface,
              borderWidth: choisi ? 0 : TRAIT, borderColor: c.filetDoux,
            }}
          >
            <T v="petit" couleur={choisi ? c.surJaune : c.encreDouce}>{libelle}</T>
          </Pressable>
        );
      })}
    </View>
  );
}

/** Un chiffre et son libelle, alignes en colonne. */
function Chiffre({ valeur, libelle }: { valeur: string; libelle: string }) {
  const c = useCouleurs();
  return (
    <View style={{ alignItems: "center", flex: 1 }}>
      <T v="sousTitre">{valeur}</T>
      <T v="legende" couleur={c.encrePale} style={{ marginTop: 2 }}>{libelle}</T>
    </View>
  );
}

/**
 * La carte d'un reseau social.
 *
 * ELLE DIT CE QUI MANQUE, PAS « BIENTOT ». Un compte non branche affiche
 * la raison exacte -- TikTok exige une validation de plusieurs jours,
 * un jeton Instagram expire au bout de 60 jours. Une promesse vague
 * n'aide personne a savoir quoi faire.
 */
function CarteReseau({ nom, icone, r }: {
  nom: string; icone: keyof typeof Ionicons.glyphMap; r?: Reseau;
}) {
  const c = useCouleurs();
  const connecte = !!r?.connecte;
  return (
    <Carte style={{ marginBottom: espace.m }}>
      <View style={{ flexDirection: "row", alignItems: "center", gap: espace.s }}>
        <Ionicons name={icone} size={22} color={c.encre} />
        <View style={{ flex: 1 }}>
          <T v="sousTitre">{nom}</T>
          {!!r?.identifiant && (
            <T v="petit" couleur={c.encreDouce}>@{r.identifiant}</T>
          )}
        </View>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
          <View style={{ width: 8, height: 8, borderRadius: 4,
                         backgroundColor: connecte ? c.gain : c.encrePale }} />
          <T v="petit" couleur={connecte ? c.gain : c.encrePale}>
            {connecte ? "connecte" : "non connecte"}
          </T>
        </View>
      </View>

      {connecte ? (
        <View style={{ flexDirection: "row", marginTop: espace.m }}>
          <Chiffre valeur={String(r?.abonnes ?? "—")} libelle="abonnes" />
          <Chiffre valeur={String(r?.publications ?? "—")} libelle="publications" />
          <Chiffre valeur={String(r?.abonnements ?? "—")} libelle="abonnements" />
        </View>
      ) : (
        !!r?.detail && (
          <T v="petit" couleur={c.encreDouce} style={{ marginTop: espace.s }}>
            {r.detail}
          </T>
        )
      )}
    </Carte>
  );
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

function LecteurVoix({ chemin }: { chemin: string }) {
  const c = useCouleurs();
  const [url, setUrl] = React.useState<string | null>(null);
  const [enLecture, setEnLecture] = React.useState(false);
  const son = React.useRef<Audio.Sound | null>(null);

  React.useEffect(() => {
    let vivant = true;
    urlSignee(chemin).then((u) => { if (vivant) setUrl(u); });
    return () => {
      vivant = false;
      son.current?.unloadAsync();
    };
  }, [chemin]);

  const basculer = async () => {
    if (!url) return;
    if (!son.current) {
      const { sound } = await Audio.Sound.createAsync(
        { uri: url }, { shouldPlay: true },
        (statut) => { if (statut.isLoaded && statut.didJustFinish) setEnLecture(false); });
      son.current = sound;
      setEnLecture(true);
      return;
    }
    const statut = await son.current.getStatusAsync();
    if (statut.isLoaded && statut.isPlaying) {
      await son.current.pauseAsync();
      setEnLecture(false);
    } else {
      await son.current.playFromPositionAsync(
        statut.isLoaded && statut.didJustFinish ? 0 : (statut.isLoaded ? statut.positionMillis : 0));
      setEnLecture(true);
    }
  };

  return (
    <Pressable onPress={basculer} disabled={!url} style={{
      flexDirection: "row", alignItems: "center", backgroundColor: c.creux,
      borderRadius: rayon.s, paddingVertical: espace.s, paddingHorizontal: espace.m,
      marginTop: espace.s, alignSelf: "flex-start", opacity: url ? 1 : 0.5,
    }}>
      <Ionicons name={enLecture ? "pause" : "play"} size={16} color={c.encre} />
      <T v="petit" style={{ marginLeft: espace.xs }}>Voix</T>
    </Pressable>
  );
}

function LecteurVideo({ chemin }: { chemin: string }) {
  const c = useCouleurs();
  const [url, setUrl] = React.useState<string | null>(null);
  React.useEffect(() => {
    let vivant = true;
    urlSignee(chemin).then((u) => { if (vivant) setUrl(u); });
    return () => { vivant = false; };
  }, [chemin]);

  if (!url) {
    return (
      <View style={{ width: "100%", aspectRatio: 9 / 16, borderRadius: rayon.m,
                     backgroundColor: c.creux, marginTop: espace.m }} />
    );
  }
  return (
    <Video
      source={{ uri: url }}
      style={{ width: "100%", aspectRatio: 9 / 16, borderRadius: rayon.m, marginTop: espace.m }}
      useNativeControls
      resizeMode={ResizeMode.COVER}
      isLooping
    />
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
      {pub.chemin_video ? (
        // La video contient deja photo + voix assemblees -- pas besoin
        // de les montrer une 2e fois a cote.
        <LecteurVideo chemin={pub.chemin_video} />
      ) : (
        <>
          {pub.chemin_photo && <PhotoPublication chemin={pub.chemin_photo} />}
          {pub.chemin_voix && <LecteurVoix chemin={pub.chemin_voix} />}
        </>
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
  const [section, setSection] = React.useState<Section>("reseaux");
  const [reseaux, setReseaux] = React.useState<EtatReseaux | null>(null);

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

  React.useEffect(() => {
    let vivant = true;
    etatReseaux().then((e) => { if (vivant) setReseaux(e); });
    return () => { vivant = false; };
  }, []);

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

      <BarreSections actif={section} surChoix={setSection} />

      {/* ----- RESEAUX : ou Luna publie, et ce qui manque ----- */}
      {section === "reseaux" && (
        <>
          <CarteReseau nom="Instagram" icone="logo-instagram"
                       r={reseaux?.instagram} />
          <CarteReseau nom="TikTok" icone="logo-tiktok"
                       r={reseaux?.tiktok} />
          {reseaux === null && <Chargement />}
          {!!reseaux && (
            <T v="legende" couleur={c.encrePale}
               style={{ textAlign: "center", marginTop: espace.s }}>
              releve {quandCourt(reseaux.vu_le)}
            </T>
          )}
        </>
      )}

      {/* ----- ATELIER : demander une publication, suivre la file ----- */}
      {section === "atelier" && (
        <>
          <Carte style={{ marginBottom: espace.l }}>
            <T v="sousTitre">Nouvelle publication</T>
            <T v="petit" couleur={c.encreDouce} style={{ marginTop: 2, marginBottom: espace.m }}>
              Laisse vide pour que Luna choisisse elle-meme.
            </T>
            <TextInput
              value={demande}
              onChangeText={setDemande}
              placeholder="ex. un cafe avec ses copines apres les cours"
              placeholderTextColor={c.encrePale}
              multiline
              style={{
                borderWidth: TRAIT, borderColor: c.filet, borderRadius: rayon.s,
                padding: espace.m, minHeight: 60, color: c.encre,
                marginBottom: espace.m, textAlignVertical: "top",
              }}
            />
            <Bouton
              titre={enCours ? "Une generation est en cours..." : "Generer"}
              onPress={surGenerer}
              desactive={envoi || enCours}
            />
          </Carte>

          <T v="sousTitre" style={{ marginBottom: espace.m }}>Ses publications</T>
          {liste === null ? (
            <Chargement />
          ) : liste.length === 0 ? (
            <Vide titre="Rien encore"
                  detail="Demande une publication ci-dessus." />
          ) : (
            liste.map((pub) => <CartePublication key={pub.id} pub={pub} />)
          )}
        </>
      )}

      {/* ----- LUNA : qui elle est ----- */}
      {section === "personnage" && (
        p ? <CartePersona p={p} />
          : <View style={{ marginBottom: espace.l }}><Chargement /></View>
      )}

    </ScrollView>
  );
}
