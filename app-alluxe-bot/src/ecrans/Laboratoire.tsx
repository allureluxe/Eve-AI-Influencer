import React from "react";
import { RefreshControl, ScrollView, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Carte, EnTete, T, Vide, useCouleurs } from "../composants/base";
import { espace, rayon } from "../theme";
import { labStatus, labStrategies, LabStatus, LabStrategy } from "../services/lab";

const LABELS: Record<string,string> = {
  IDLE:"EN ATTENTE", IDEATED:"IDEE", BACKTEST:"BACKTEST",
  CANDIDATE:"CANDIDAT", FORWARD_TEST:"FORWARD TEST",
  INCUBATION:"INCUBATION", VALIDATED:"VALIDEE",
  "ARCHIVED-WEAK":"ARCHIVEE", "RETIRED-WEAK":"RETIRÉE", ERROR:"ERREUR",
};

function Stat({ titre, valeur }: { titre:string; valeur:string|number }) {
  const c=useCouleurs();
  return <View style={{flex:1, padding:espace.m, backgroundColor:c.creux, borderRadius:rayon.s}}>
    <T v="etiquette">{titre}</T><T v="chiffre" style={{marginTop:4}}>{valeur}</T>
  </View>;
}

function Ligne({ item }: { item: LabStrategy }) {
  const c=useCouleurs();
  const b=item.backtest ?? {};
  const f=item.forward_test ?? {};
  return <Carte style={{marginBottom:espace.m}}>
    <View style={{flexDirection:"row",justifyContent:"space-between",gap:8}}>
      <View style={{flex:1}}>
        <T v="sousTitre">{item.agent}</T>
        <T v="petit" style={{marginTop:2}} numberOfLines={1}>{item.strategy_id}</T>
      </View>
      <T v="etiquette" couleur={item.stage==="VALIDATED"?c.gain:c.encreDouce}>
        {LABELS[item.stage] ?? item.stage}
      </T>
    </View>
    <View style={{flexDirection:"row",gap:8,marginTop:espace.m}}>
      <Stat titre="TRADES" valeur={b.trades ?? 0}/>
      <Stat titre="PF" valeur={b.profit_factor ?? "—"}/>
      <Stat titre="WIN %" valeur={b.win_rate ?? "—"}/>
      <Stat titre="FWD PF" valeur={f.profit_factor ?? "—"}/>
    </View>
    <T v="petit" style={{marginTop:espace.m}}>
      {item.reason || "Aucun commentaire"}
    </T>
  </Carte>;
}

export function EcranLaboratoire() {
  const c=useCouleurs();
  const marges=useSafeAreaInsets();
  const [status,setStatus]=React.useState<LabStatus|null>(null);
  const [items,setItems]=React.useState<LabStrategy[]>([]);
  const [refreshing,setRefreshing]=React.useState(false);

  const charger=React.useCallback(async()=>{
    try { const [s,x]=await Promise.all([labStatus(),labStrategies(30)]); setStatus(s); setItems(x); }
    catch {}
  },[]);

  React.useEffect(()=>{ charger(); const id=setInterval(charger,10000); return()=>clearInterval(id); },[charger]);

  const refresh=async()=>{setRefreshing(true);await charger();setRefreshing(false);};

  return <ScrollView style={{backgroundColor:c.fond}}
    contentContainerStyle={{padding:espace.l,paddingTop:marges.top+espace.m,paddingBottom:marges.bottom+espace.xxl}}
    refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh}/>}>
    <EnTete titre="Laboratoire" sousTitre="Stratégies testées en parallèle, sans ordre réel"/>
    <Carte accent style={{marginBottom:espace.m}}>
      <T v="etiquette">MOTEUR</T>
      <T v="titre" style={{marginTop:4}}>{LABELS[status?.stage ?? "IDLE"] ?? "EN ATTENTE"}</T>
      <T v="petit" style={{marginTop:4}}>{status?.detail ?? "Le service du laboratoire n'a pas encore publié son état."}</T>
      <View style={{flexDirection:"row",gap:8,marginTop:espace.m}}>
        <Stat titre="TESTS" valeur={status?.completed ?? 0}/>
        <Stat titre="CANDIDATS" valeur={status?.candidates ?? 0}/>
        <Stat titre="VALIDÉES" valeur={status?.validated ?? 0}/>
      </View>
    </Carte>

    <T v="etiquette" style={{marginBottom:espace.m}}>PIPELINE</T>
    <T v="petit" style={{marginBottom:espace.l}}>
      Idée → backtest historique → seuil 100 trades / PF 1,20 / win 40 % / payoff &gt; 1 → forward test → incubation → validée.
    </T>

    {items.length ? items.map(x=><Ligne key={x.strategy_id} item={x}/>) :
      <Vide titre="Aucune stratégie enregistrée" detail="Le laboratoire commencera à remplir le carnet dès que son service sera lancé."/>}
  </ScrollView>;
}
