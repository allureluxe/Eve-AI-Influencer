/**
 * Onglet Luna — centre de pilotage contenu + croissance.
 *
 * Le telephone choisit le format et la cible ; Supabase depose le job ;
 * le worker VPS genere et publie ; la meme page suit ensuite les
 * publications, les Stories a conserver, les comptes et les indicateurs
 * de monétisation.
 */
import React from "react";
import {
  Image, Pressable, RefreshControl, ScrollView, Switch, TextInput, View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Audio, ResizeMode, Video } from "expo-av";
import { Ionicons } from "@expo/vector-icons";
import {
  demanderGeneration, performances, Publication, Persona,
  FormatLuna, PlateformeLuna, TrackMonetisation, TypeLieu,
  StatutPublication, persona as chargerPersona, publications, urlSignee,
  PerformanceLuna,
} from "../services/luna";
import { espace, rayon, TRAIT } from "../theme";
import { Bouton, Carte, Chargement, Logo, T, useCouleurs, Vide } from "../composants/base";
import { EtatReseaux, Reseau, etatReseaux } from "../services/reseaux";

const RYTHME_MS = 15_000;

const LIBELLE_STATUT: Record<StatutPublication, string> = {
  en_attente: "En attente",
  en_cours: "En cours",
  terminee: "Terminee",
  echec: "Echouee",
};

const FORMAT_LABELS: Record<FormatLuna, string> = {
  legacy: "Auto",
  feed_photo: "Post photo",
  story: "Story",
  highlight_story: "Story + Highlight",
  reel: "Reel",
  tiktok_short: "TikTok court",
  tiktok_rewards: "TikTok 1 min+",
  tiktok_photo: "TikTok photo",
};

const FORMATS: { id: FormatLuna; icon: keyof typeof Ionicons.glyphMap; desc: string }[] = [
  { id: "feed_photo", icon: "image-outline", desc: "3:4" },
  { id: "story", icon: "phone-portrait-outline", desc: "9:16" },
  { id: "highlight_story", icon: "bookmark-outline", desc: "9:16" },
  { id: "reel", icon: "play-circle-outline", desc: "10 s • 9:16" },
  { id: "tiktok_short", icon: "logo-tiktok", desc: "10 s • 9:16" },
  { id: "tiktok_rewards", icon: "logo-tiktok", desc: "60 s+ • 9:16" },
];

const LIEUX: { id: TypeLieu; label: string; emoji: string }[] = [
  { id: "restaurant", label: "Restaurant", emoji: "🍽️" },
  { id: "bar", label: "Bar", emoji: "🍸" },
  { id: "cafe", label: "Café", emoji: "☕" },
  { id: "landmark", label: "Lieu", emoji: "📍" },
  { id: "travel", label: "Voyage", emoji: "✈️" },
];

const HIGHLIGHTS = ["Metz", "Restaurants", "Bars", "Cafes", "Voyages", "Looks", "Luna"];

const MONETISATION = [
  { id: "instagram_gifts" as TrackMonetisation, platform: "Instagram", title: "Gifts", target: 5000, note: "Abonnes • verification dans le tableau de bord" },
  { id: "instagram_subscriptions" as TrackMonetisation, platform: "Instagram", title: "Abonnements", target: 0, note: "Disponibilite a verifier dans le tableau de bord" },
  { id: "tiktok_creator_rewards" as TrackMonetisation, platform: "TikTok", title: "Creator Rewards", target: 10000, note: "10k abonnes + 100k vues/30 j + videos d’au moins 1 min" },
  { id: "tiktok_series" as TrackMonetisation, platform: "TikTok", title: "Series", target: 10000, note: "10k abonnes • compte et activite eligibles a verifier" },
  { id: "brand_deals" as TrackMonetisation, platform: "Multi", title: "Partenariats", target: 0, note: "Media kit, conformité et audience engagee" },
];

function couleurStatut(c: ReturnType<typeof useCouleurs>, s: StatutPublication): string {
  if (s === "terminee") return c.gain;
  if (s === "echec") return c.perte;
  if (s === "en_cours") return c.vigilance;
  return c.encrePale;
}

function quandCourt(iso: string): string {
  const min = Math.max(0, (Date.now() - new Date(iso).getTime()) / 60000);
  if (min < 2) return "a l'instant";
  if (min < 60) return "il y a " + Math.round(min) + " min";
  if (min < 48 * 60) return "il y a " + Math.round(min / 60) + " h";
  return "il y a " + Math.round(min / 1440) + " j";
}

function formatCourt(p: Publication): string {
  const lieu = p.location_name ? " • " + p.location_name : "";
  return (FORMAT_LABELS[p.content_format] ?? p.content_format) + lieu;
}

function BarreSections({ actif, surChoix }: {
  actif: Section; surChoix: (s: Section) => void;
}) {
  const c = useCouleurs();
  return (
    <View style={{ flexDirection: "row", gap: espace.s, marginBottom: espace.l }}>
      {([
        ["dashboard", "Pilotage"],
        ["creer", "Créer"],
        ["planning", "Planning"],
        ["personnage", "Luna"],
      ] as [Section, string][]).map(([cle, libelle]) => {
        const choisi = cle === actif;
        return (
          <Pressable
            key={cle}
            onPress={() => surChoix(cle)}
            accessibilityRole="button"
            accessibilityState={{ selected: choisi }}
            style={{
              flex: 1, paddingVertical: espace.s, borderRadius: rayon.l,
              alignItems: "center", backgroundColor: choisi ? c.jauneAplat : c.surface,
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

type Section = "dashboard" | "creer" | "planning" | "personnage";

function Chiffre({ valeur, libelle }: { valeur: string; libelle: string }) {
  const c = useCouleurs();
  return (
    <View style={{ alignItems: "center", flex: 1 }}>
      <T v="sousTitre">{valeur}</T>
      <T v="legende" couleur={c.encrePale} style={{ marginTop: 2 }}>{libelle}</T>
    </View>
  );
}

function BarreProgression({ valeur, cible }: { valeur: number; cible: number }) {
  const c = useCouleurs();
  const ratio = cible > 0 ? Math.max(0, Math.min(1, valeur / cible)) : 0;
  return (
    <View style={{ marginTop: espace.s }}>
      <View style={{ height: 7, backgroundColor: c.creux, borderRadius: 999, overflow: "hidden" }}>
        <View style={{ width: `${Math.round(ratio * 100)}%`, height: 7, backgroundColor: c.jaune }} />
      </View>
    </View>
  );
}

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
          {!!r?.identifiant && <T v="petit" couleur={c.encreDouce}>@{r.identifiant}</T>}
        </View>
        <T v="petit" couleur={connecte ? c.gain : c.encrePale}>
          {connecte ? "connecte" : "non connecte"}
        </T>
      </View>
      {connecte ? (
        <View style={{ flexDirection: "row", marginTop: espace.m }}>
          <Chiffre valeur={String(r?.abonnes ?? "—")} libelle="abonnes" />
          <Chiffre valeur={String(r?.publications ?? "—")} libelle="publications" />
          <Chiffre valeur={String(r?.abonnements ?? "—")} libelle="abonnements" />
        </View>
      ) : (
        !!r?.detail && <T v="petit" couleur={c.encreDouce} style={{ marginTop: espace.s }}>{r.detail}</T>
      )}
    </Carte>
  );
}

function CarteMonetisation({
  track, plateforme, valeur, performances30j,
}: {
  track: typeof MONETISATION[number];
  plateforme?: Reseau;
  valeur: number;
  performances30j: PerformanceLuna[];
}) {
  const c = useCouleurs();
  const vues30j = performances30j.reduce((s, p) => s + Number(p.views || 0), 0);
  const followers = plateforme?.abonnes ?? valeur;
  const cible = track.target;
  const pret = cible > 0 ? followers >= cible : false;
  return (
    <Carte style={{ marginBottom: espace.m }}>
      <View style={{ flexDirection: "row", alignItems: "flex-start", gap: espace.m }}>
        <View style={{ flex: 1 }}>
          <T v="petit" couleur={c.encrePale}>{track.platform}</T>
          <T v="sousTitre" style={{ marginTop: 2 }}>{track.title}</T>
        </View>
        <T v="petit" couleur={pret ? c.gain : c.encreDouce}>
          {pret ? "seuil atteint" : cible ? `${Math.min(100, Math.round((followers / cible) * 100))}%` : "a verifier"}
        </T>
      </View>
      {cible > 0 && (
        <>
          <BarreProgression valeur={followers} cible={cible} />
          <T v="legende" style={{ marginTop: 5 }}>{followers.toLocaleString("fr-FR")} / {cible.toLocaleString("fr-FR")} abonnes</T>
        </>
      )}
      <T v="petit" couleur={c.encreDouce} style={{ marginTop: espace.s }}>{track.note}</T>
      {track.id === "tiktok_creator_rewards" && (
        <T v="legende" style={{ marginTop: espace.xs }}>
          Vues mesurees par l'app sur les 30 derniers jours : {vues30j.toLocaleString("fr-FR")}
        </T>
      )}
    </Carte>
  );
}

function PhotoPublication({ chemin, ratio }: { chemin: string; ratio: string }) {
  const c = useCouleurs();
  const [url, setUrl] = React.useState<string | null>(null);
  React.useEffect(() => {
    let vivant = true;
    urlSignee(chemin).then((u) => { if (vivant) setUrl(u); });
    return () => { vivant = false; };
  }, [chemin]);

  if (!url) {
    return <View style={{ width: "100%", aspectRatio: ratio === "16:9" ? 16 / 9 : 3 / 4, borderRadius: rayon.m, backgroundColor: c.creux, marginTop: espace.m }} />;
  }
  return <Image source={{ uri: url }} style={{ width: "100%", aspectRatio: ratio === "16:9" ? 16 / 9 : 3 / 4, borderRadius: rayon.m, marginTop: espace.m }} />;
}

function LecteurVoix({ chemin }: { chemin: string }) {
  const c = useCouleurs();
  const [url, setUrl] = React.useState<string | null>(null);
  const [enLecture, setEnLecture] = React.useState(false);
  const son = React.useRef<Audio.Sound | null>(null);

  React.useEffect(() => {
    let vivant = true;
    urlSignee(chemin).then((u) => { if (vivant) setUrl(u); });
    return () => { vivant = false; son.current?.unloadAsync(); };
  }, [chemin]);

  const basculer = async () => {
    if (!url) return;
    if (!son.current) {
      const { sound } = await Audio.Sound.createAsync(
        { uri: url }, { shouldPlay: true },
        (statut) => { if (statut.isLoaded && statut.didJustFinish) setEnLecture(false); },
      );
      son.current = sound;
      setEnLecture(true);
      return;
    }
    const statut = await son.current.getStatusAsync();
    if (statut.isLoaded && statut.isPlaying) {
      await son.current.pauseAsync(); setEnLecture(false);
    } else {
      await son.current.playFromPositionAsync(
        statut.isLoaded && statut.didJustFinish ? 0 : (statut.isLoaded ? statut.positionMillis : 0),
      );
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

  if (!url) return <View style={{ width: "100%", aspectRatio: 9 / 16, borderRadius: rayon.m, backgroundColor: c.creux, marginTop: espace.m }} />;
  return (
    <Video
      source={{ uri: url }} style={{ width: "100%", aspectRatio: 9 / 16, borderRadius: rayon.m, marginTop: espace.m }}
      useNativeControls resizeMode={ResizeMode.COVER} isLooping
    />
  );
}

function CartePublication({ pub }: { pub: Publication }) {
  const c = useCouleurs();
  const schedule = pub.scheduled_at
    ? new Date(pub.scheduled_at).toLocaleString("fr-FR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })
    : null;
  const meta = [
    FORMAT_LABELS[pub.content_format] ?? pub.content_format,
    pub.platform === "both" ? "Instagram + TikTok" : pub.platform === "tiktok" ? "TikTok" : "Instagram",
    pub.aspect_ratio,
  ].join(" • ");
  return (
    <Carte style={{ marginBottom: espace.m }}>
      <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" }}>
        <View style={{ flex: 1, marginRight: espace.s }}>
          <T v="petit" couleur={c.encreDouce}>{meta}</T>
          <T v="sousTitre" style={{ marginTop: 2 }}>{pub.location_name ?? "Luna"}</T>
        </View>
        <T v="legende">{schedule ? "prévu " + schedule : quandCourt(pub.created_at)}</T>
      </View>

      <T v="sousTitre" couleur={couleurStatut(c, pub.statut)} style={{ marginTop: 4 }}>
        {LIBELLE_STATUT[pub.statut]}
      </T>

      {!!pub.demande && <T v="petit" couleur={c.encreDouce} style={{ marginTop: espace.s }}>{pub.demande}</T>}
      {!!pub.legende && <T v="corps" style={{ marginTop: espace.s }}>{pub.legende}</T>}

      {pub.chemin_video ? (
        <LecteurVideo chemin={pub.chemin_video} />
      ) : (
        <>
          {pub.chemin_photo && <PhotoPublication chemin={pub.chemin_photo} ratio={pub.aspect_ratio} />}
          {pub.chemin_voix && <LecteurVoix chemin={pub.chemin_voix} />}
        </>
      )}

      {(pub.location_type || pub.highlight_name || pub.call_to_action) && (
        <View style={{ marginTop: espace.s }}>
          {!!pub.location_type && <T v="legende">Lieu : {pub.location_type}</T>}
          {!!pub.highlight_name && <T v="legende">Highlight : {pub.highlight_name} • statut {pub.highlight_name && pub.chemin_photo ? "à enregistrer / suivi serveur" : "planifie"}</T>}
          {!!pub.call_to_action && <T v="legende">CTA : {pub.call_to_action}</T>}
        </View>
      )}

      {!!pub.publish_requested && (
        <T v="legende" couleur={c.gain} style={{ marginTop: espace.s }}>
          publication demandee • contenu IA signale : {pub.ai_disclosure ? "oui" : "non"}
        </T>
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

function CarteHighlight({ nom, publications: pubs }: { nom: string; publications: Publication[] }) {
  const c = useCouleurs();
  const stories = pubs.filter((p) => p.highlight_name === nom);
  const aSauver = stories.filter((p) => p.statut === "terminee").length;
  const enregistrees = stories.filter((p) => p.highlight_status === "saved").length;
  const aEnregistrer = stories.filter((p) => p.highlight_status === "pending_manual").length;
  return (
    <Carte style={{ marginBottom: espace.m }}>
      <View style={{ flexDirection: "row", alignItems: "center" }}>
        <Ionicons name="bookmark-outline" size={20} color={c.encre} />
        <View style={{ flex: 1, marginLeft: espace.s }}>
          <T v="sousTitre">{nom}</T>
          <T v="legende">
            {stories.length} story • {aSauver} prête(s) • {enregistrees} enregistrée(s)
            {aEnregistrer ? ` • ${aEnregistrer} à enregistrer` : ""}
          </T>
        </View>
        <T v="petit" couleur={enregistrees ? c.gain : stories.length ? c.vigilance : c.encrePale}>
          {enregistrees ? "enregistre" : stories.length ? "a traiter" : "vide"}
        </T>
      </View>
    </Carte>
  );
}

function Pill({ texte, actif, onPress, icon }: {
  texte: string; actif: boolean; onPress: () => void; icon?: keyof typeof Ionicons.glyphMap;
}) {
  const c = useCouleurs();
  return (
    <Pressable
      onPress={onPress}
      style={{
        borderRadius: rayon.rond, paddingVertical: espace.s, paddingHorizontal: espace.m,
        backgroundColor: actif ? c.jauneAplat : c.surface,
        borderWidth: actif ? 0 : TRAIT, borderColor: c.filetDoux,
        flexDirection: "row", alignItems: "center", marginRight: espace.s, marginBottom: espace.s,
      }}
    >
      {icon && <Ionicons name={icon} size={15} color={actif ? c.surJaune : c.encreDouce} />}
      <T v="petit" couleur={actif ? c.surJaune : c.encreDouce} style={{ marginLeft: icon ? espace.xs : 0 }}>{texte}</T>
    </Pressable>
  );
}

function CarteCreation({ surCreer, envoi, enCours }: {
  surCreer: (spec: Creation) => Promise<void>;
  envoi: boolean;
  enCours: boolean;
}) {
  const c = useCouleurs();
  const [format, setFormat] = React.useState<FormatLuna>("feed_photo");
  const [plateforme, setPlateforme] = React.useState<PlateformeLuna>("instagram");
  const [lieu, setLieu] = React.useState<TypeLieu | null>(null);
  const [highlight, setHighlight] = React.useState("Metz");
  const [demande, setDemande] = React.useState("");
  const [publier, setPublier] = React.useState(true);
  const [objectif, setObjectif] = React.useState<TrackMonetisation>("growth");

  React.useEffect(() => {
    if (format === "tiktok_short" || format === "tiktok_rewards" || format === "tiktok_photo") {
      setPlateforme("tiktok");
      setObjectif(format === "tiktok_rewards" ? "tiktok_creator_rewards" : "growth");
    } else {
      setPlateforme("instagram");
      if (format === "highlight_story") setObjectif("growth");
    }
  }, [format]);

  const creer = async () => {
    const demandeFinale = demande.trim() || (
      lieu === "restaurant" ? "Trouve un restaurant photogénique et construis un contenu découverte sans inventer une visite." :
      lieu === "bar" ? "Trouve un bar Instagrammable et construis un contenu découverte sans inventer une visite." :
      lieu === "cafe" ? "Trouve un café photogénique et construis un contenu découverte sans inventer une visite." :
      lieu === "landmark" ? "Trouve un lieu iconique et construis une scène photo réaliste de Luna." :
      lieu === "travel" ? "Imagine une escapade réaliste de Luna dans une destination identifiable." :
      "Choisis une idee qui sert la croissance de Luna aujourd’hui."
    );
    await surCreer({
      demande: demandeFinale,
      content_format: format,
      platform: plateforme,
      location_type: lieu,
      highlight_name: format === "highlight_story" ? highlight : null,
      publish_requested: publier,
      monetization_track: objectif,
      ai_disclosure: true,
    });
  };

  return (
    <Carte accent style={{ marginBottom: espace.l }}>
      <T v="sousTitre">Créer un contenu</T>
      <T v="petit" couleur={c.encreDouce} style={{ marginTop: 2, marginBottom: espace.m }}>
        Le serveur s’occupe de la génération, de la publication et du suivi.
      </T>

      <T v="etiquette" style={{ marginBottom: espace.s }}>FORMAT</T>
      <View style={{ flexDirection: "row", flexWrap: "wrap" }}>
        {FORMATS.map((f) => (
          <Pill key={f.id} texte={f.desc + " • " + FORMAT_LABELS[f.id]} icon={f.icon} actif={format === f.id} onPress={() => setFormat(f.id)} />
        ))}
      </View>

      <T v="etiquette" style={{ marginTop: espace.s, marginBottom: espace.s }}>PLATEFORME</T>
      <View style={{ flexDirection: "row", flexWrap: "wrap" }}>
        {([
          ["instagram", "Instagram"],
          ["tiktok", "TikTok"],
          ["both", "Les deux"],
        ] as [PlateformeLuna, string][]).map(([id, label]) => (
          <Pill key={id} texte={label} actif={plateforme === id} onPress={() => setPlateforme(id)} />
        ))}
      </View>

      <T v="etiquette" style={{ marginTop: espace.s, marginBottom: espace.s }}>SUJET / LIEU</T>
      <View style={{ flexDirection: "row", flexWrap: "wrap" }}>
        <Pill texte="Libre" actif={lieu === null} onPress={() => setLieu(null)} />
        {LIEUX.map((x) => <Pill key={x.id} texte={x.emoji + " " + x.label} actif={lieu === x.id} onPress={() => setLieu(x.id)} />)}
      </View>

      {format === "highlight_story" && (
        <>
          <T v="etiquette" style={{ marginTop: espace.s, marginBottom: espace.s }}>HIGHLIGHT</T>
          <View style={{ flexDirection: "row", flexWrap: "wrap" }}>
            {HIGHLIGHTS.map((nom) => <Pill key={nom} texte={nom} actif={highlight === nom} onPress={() => setHighlight(nom)} />)}
          </View>
        </>
      )}

      <T v="etiquette" style={{ marginTop: espace.s, marginBottom: espace.s }}>OBJECTIF</T>
      <View style={{ flexDirection: "row", flexWrap: "wrap" }}>
        {MONETISATION.map((m) => (
          <Pill key={m.id} texte={m.title} actif={objectif === m.id} onPress={() => setObjectif(m.id)} />
        ))}
      </View>

      <TextInput
        value={demande} onChangeText={setDemande}
        placeholder="Ex. coucher de soleil à Metz, terrasse, tenue du jour..."
        placeholderTextColor={c.encrePale} multiline
        style={{
          borderWidth: TRAIT, borderColor: c.filet, borderRadius: rayon.s,
          padding: espace.m, minHeight: 74, color: c.encre, marginTop: espace.s,
          textAlignVertical: "top",
        }}
      />

      <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: espace.m }}>
        <View style={{ flex: 1 }}>
          <T v="petit">Publier automatiquement après génération</T>
          <T v="legende">Le bouton active seulement la demande de publication ; le worker garde le contrôle du résultat.</T>
        </View>
        <Switch value={publier} onValueChange={setPublier} />
      </View>

      <Bouton
        titre={envoi || enCours ? "Job déjà en cours..." : "Créer maintenant"}
        onPress={creer} desactive={envoi || enCours}
      />
    </Carte>
  );
}

type Creation = {
  demande: string;
  content_format: FormatLuna;
  platform: PlateformeLuna;
  location_type: TypeLieu | null;
  highlight_name: string | null;
  publish_requested: boolean;
  monetization_track: TrackMonetisation;
  ai_disclosure: boolean;
};

function CartePersona({ p }: { p: Persona }) {
  const c = useCouleurs();
  return (
    <Carte accent style={{ marginBottom: espace.l }}>
      <T v="titre">{p.prenom}, {p.age} ans</T>
      <T v="petit" couleur={c.encreDouce} style={{ marginTop: 2 }}>{p.metier}</T>
      {!!p.contexte && <T v="corps" style={{ marginTop: espace.m }}>{p.contexte}</T>}
      {p.caractere.length > 0 && (
        <View style={{ marginTop: espace.m }}>
          {p.caractere.map((trait, i) => <T key={i} v="petit" couleur={c.encreDouce} style={{ marginTop: i ? 2 : 0 }}>• {trait}</T>)}
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
  const [stats, setStats] = React.useState<PerformanceLuna[]>([]);
  const [reseaux, setReseaux] = React.useState<EtatReseaux | null>(null);
  const [erreur, setErreur] = React.useState("");
  const [envoi, setEnvoi] = React.useState(false);
  const [rafraichit, setRafraichit] = React.useState(false);
  const [section, setSection] = React.useState<Section>("dashboard");

  const charger = React.useCallback(async () => {
    try {
      const [pers, pubs, perf, rs] = await Promise.all([
        chargerPersona(), publications(), performances(), etatReseaux(),
      ]);
      setP(pers); setListe(pubs); setStats(perf); setReseaux(rs); setErreur("");
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
    setRafraichit(true); await charger(); setRafraichit(false);
  };

  const surCreer = async (spec: Creation) => {
    setEnvoi(true);
    try {
      await demanderGeneration(spec.demande, spec);
      await charger();
      setSection("planning");
    } catch (err: any) {
      setErreur(err?.message ?? "Impossible de creer le job");
    } finally {
      setEnvoi(false);
    }
  };

  const enCours = (liste ?? []).some((pub) => pub.statut === "en_attente" || pub.statut === "en_cours");
  const programmees = (liste ?? []).filter((pub) => pub.scheduled_at && new Date(pub.scheduled_at).getTime() > Date.now());
  const highlights = (liste ?? []).filter((pub) => pub.highlight_name);
  const stats30j = stats.filter((p) => new Date(p.measured_at).getTime() >= Date.now() - 30 * 24 * 60 * 60 * 1000);
  const vues30j = stats30j.reduce((s, x) => s + Number(x.views || 0), 0);
  const engagements = stats30j.reduce((s, x) => s + Number(x.likes || 0) + Number(x.comments || 0) + Number(x.shares || 0) + Number(x.saves || 0), 0);

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: c.fond }}
      contentContainerStyle={{ paddingTop: marges.top + espace.s, paddingHorizontal: espace.l, paddingBottom: espace.xxl }}
      refreshControl={<RefreshControl refreshing={rafraichit} onRefresh={surRafraichir} />}
    >
      <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: espace.l }}>
        <View>
          <T v="titreGrand">Luna</T>
          <T v="petit" couleur={c.encreDouce}>Studio • croissance • monetisation</T>
        </View>
        <Logo hauteur={40} />
      </View>

      {!!erreur && <T v="petit" couleur={c.perte} style={{ marginBottom: espace.m }}>{erreur}</T>}

      <BarreSections actif={section} surChoix={setSection} />

      {section === "dashboard" && (
        <>
          <View style={{ flexDirection: "row", gap: espace.s, marginBottom: espace.m }}>
            <Carte style={{ flex: 1 }}>
              <T v="etiquette">Prochaines 36 h</T>
              <T v="titre" style={{ marginTop: 2 }}>{programmees.length}</T>
              <T v="legende">contenus planifies</T>
            </Carte>
            <Carte style={{ flex: 1 }}>
              <T v="etiquette">Performance 30 j</T>
              <T v="titre" style={{ marginTop: 2 }}>{vues30j.toLocaleString("fr-FR")}</T>
              <T v="legende">vues mesurees</T>
            </Carte>
          </View>

          <T v="sousTitre" style={{ marginBottom: espace.m }}>Comptes</T>
          <CarteReseau nom="Instagram" icone="logo-instagram" r={reseaux?.instagram} />
          <CarteReseau nom="TikTok" icone="logo-tiktok" r={reseaux?.tiktok} />

          <Carte style={{ marginBottom: espace.l }}>
            <T v="sousTitre">Croissance suivie</T>
            <View style={{ flexDirection: "row", marginTop: espace.m }}>
              <Chiffre valeur={(reseaux?.instagram?.abonnes ?? 0).toLocaleString("fr-FR")} libelle="Instagram" />
              <Chiffre valeur={(reseaux?.tiktok?.abonnes ?? 0).toLocaleString("fr-FR")} libelle="TikTok" />
              <Chiffre valeur={engagements.toLocaleString("fr-FR")} libelle="engagements mesurés" />
            </View>
          </Carte>

          <T v="sousTitre" style={{ marginBottom: espace.m }}>Monétisation</T>
          {MONETISATION.map((track) => (
            <CarteMonetisation
              key={track.id}
              track={track}
              valeur={track.platform === "TikTok" ? (reseaux?.tiktok?.abonnes ?? 0) : (reseaux?.instagram?.abonnes ?? 0)}
              plateforme={track.platform === "TikTok" ? reseaux?.tiktok : reseaux?.instagram}
              performances30j={stats30j}
            />
          ))}
        </>
      )}

      {section === "creer" && (
        <>
          <CarteCreation surCreer={surCreer} envoi={envoi} enCours={enCours} />
          <Carte style={{ marginBottom: espace.l }}>
            <T v="sousTitre">Règle éditoriale lieux</T>
            <T v="petit" couleur={c.encreDouce} style={{ marginTop: espace.s }}>
              Restaurants, bars, cafés et lieux Instagrammables sont traités comme sujets de contenu. Le système recherche le lieu et évite d’inventer une visite réelle.
            </T>
            <T v="legende" style={{ marginTop: espace.s }}>
              Le contenu photoréaliste reste identifié comme IA dans les métadonnées prévues.
            </T>
          </Carte>
        </>
      )}

      {section === "planning" && (
        <>
          <Carte accent style={{ marginBottom: espace.l }}>
            <T v="sousTitre">Calendrier automatique</T>
            <T v="petit" couleur={c.encreDouce} style={{ marginTop: 3 }}>
              Le planificateur maintient une fenêtre d’environ 36 h et alimente ici les prochains contenus. Les jobs apparaissent au fur et à mesure.
            </T>
            <View style={{ flexDirection: "row", marginTop: espace.m }}>
              <Chiffre valeur={String(programmees.length)} libelle="a venir" />
              <Chiffre valeur={String(highlights.length)} libelle="stories à conserver" />
              <Chiffre valeur={enCours ? "1" : "0"} libelle="job actif" />
            </View>
          </Carte>

          <T v="sousTitre" style={{ marginBottom: espace.m }}>Prochains contenus</T>
          {programmees.length === 0
            ? <Vide titre="Pas encore de créneau visible" detail="Le planificateur remplira la fenêtre dès que le worker et Supabase sont actifs." />
            : programmees.slice(0, 12).map((pub) => <CartePublication key={pub.id} pub={pub} />)
          }

          <T v="sousTitre" style={{ marginTop: espace.l, marginBottom: espace.m }}>Stories enregistrées / Highlights</T>
          {HIGHLIGHTS.map((nom) => <CarteHighlight key={nom} nom={nom} publications={liste ?? []} />)}

          <T v="legende" couleur={c.encrePale} style={{ marginTop: espace.s, textAlign: "center" }}>
            Les Stories publiées sont suivies ici. Le passage dans le Highlight reste marqué « à enregistrer » lorsqu’il doit être fait depuis Instagram.
          </T>
        </>
      )}

      {section === "personnage" && (
        <>
          {p ? <CartePersona p={p} /> : <Chargement />}
          <Carte style={{ marginBottom: espace.l }}>
            <T v="sousTitre">Identité visuelle verrouillée</T>
            <T v="petit" couleur={c.encreDouce} style={{ marginTop: espace.s }}>
              Même visage de référence pour chaque génération : yeux gris-vert mats, cheveux blond platine à racines visibles, teint doré naturel et un seul grain de beauté.
            </T>
          </Carte>
        </>
      )}
    </ScrollView>
  );
}
