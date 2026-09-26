import React from "react";
import { RefreshControl, ScrollView, View } from "react-native";
import Svg, { Polyline, Line, Circle } from "react-native-svg";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Carte, EnTete, T, Vide, useCouleurs } from "../composants/base";
import { espace, rayon } from "../theme";
import { labStatus, labStrategies, LabStatus, LabStrategy } from "../services/lab";

const LABELS: Record<string,string> = {
  IDLE:"EN ATTENTE", IDEATED:"IDÉE", BACKTEST:"BACKTEST",
  CANDIDATE:"CANDIDAT", FORWARD_TEST:"FORWARD TEST",
  INCUBATION:"INCUBATION", VALIDATED:"VALIDÉE",
  "ARCHIVED-WEAK":"ARCHIVÉE", "RETIRED-WEAK":"RETRAIT", ERROR:"ERREUR",
};

const PIPELINE = [
  ["IDEATED","IDÉE"], ["BACKTEST","BACKTEST"], ["CANDIDATE","CANDIDAT"],
  ["FORWARD_TEST","FORWARD"], ["INCUBATION","INCUBATION"], ["VALIDATED","VALIDÉE"],
] as const;

function num(v: unknown, fallback = 0) {
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

function Stat({ titre, valeur, compact=false }: { titre:string; valeur:string|number; compact?:boolean }) {
  const c=useCouleurs();
  return <View style={{flex:1, minWidth: compact ? 72 : 0, padding:compact ? espace.s : espace.m, backgroundColor:c.creux, borderRadius:rayon.s}}>
    <T v="etiquette">{titre}</T><T v="chiffre" style={{marginTop:4}}>{valeur}</T>
  </View>;
}

function Pulse({ active }: { active:boolean }) {
  const c=useCouleurs();
  return <View style={{width:10,height:10,borderRadius:5,backgroundColor:active?c.gain:c.encrePale,marginRight:8}} />;
}

function MiniCurve({ values }: { values:number[] }) {
  const c=useCouleurs();
  if (values.length < 2) return <View style={{height:54,justifyContent:"center"}}><T v="legende">courbe en attente de données</T></View>;
  const w=300,h=54,p=5;
  const lo=Math.min(...values), hi=Math.max(...values);
  const span=hi-lo || 1;
  const points=values.map((v,i)=>`${p+(i/(values.length-1))*(w-p*2)},${h-p-((v-lo)/span)*(h-p*2)}`).join(" ");
  return <Svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`}>
    <Line x1="0" y1={h-1} x2={w} y2={h-1} stroke={c.filetDoux} strokeWidth={1}/>
    <Polyline points={points} fill="none" stroke={c.jaune} strokeWidth={2.5}/>
    <Circle cx={p+(values.length-1)/(values.length-1)*(w-p*2)} cy={h-p-((values[values.length-1]-lo)/span)*(h-p*2)} r={3.5} fill={c.jaune}/>
  </Svg>;
}

function Pipeline({ stage }: { stage:string }) {
  const c=useCouleurs();
  const idx=Math.max(0, PIPELINE.findIndex(([s])=>s===stage));
  return <View>
    <View style={{flexDirection:"row",alignItems:"center"}}>
      {PIPELINE.map(([s,label],i)=><React.Fragment key={s}>
        <View style={{flex:1,alignItems:"center"}}>
          <View style={{
            width:24,height:24,borderRadius:12,
            backgroundColor:i<=idx?c.jaune:c.creux,
            borderWidth: i<=idx ? 0 : 1,
            borderColor:c.filetDoux,
            alignItems:"center",justifyContent:"center"
          }}>
            <T v="legende" couleur={i<=idx?c.surJaune:c.encrePale}>{i+1}</T>
          </View>
          <T v="legende" style={{marginTop:5,textAlign:"center"}}>{label}</T>
        </View>
        {i<PIPELINE.length-1?<View style={{height:1,flex:0.7,backgroundColor:i<idx?c.jaune:c.filetDoux,marginTop:-17}}/>:null}
      </React.Fragment>)}
    </View>
  </View>;
}

function Ligne({ item }: { item: LabStrategy }) {
  const c=useCouleurs();
  const b=item.backtest ?? {};
  const f=item.forward_test ?? {};
  const pf=num(b.profit_factor), win=num(b.win_rate), fwd=num(f.profit_factor);
  return <Carte style={{marginBottom:espace.m}}>
    <View style={{flexDirection:"row",justifyContent:"space-between",gap:8}}>
      <View style={{flex:1}}>
        <T v="sousTitre">{item.agent}</T>
        <T v="petit" style={{marginTop:2}} numberOfLines={1}>{item.strategy_id}</T>
      </View>
      <T v="etiquette" couleur={item.stage==="VALIDATED"?c.gain:item.stage==="RETIRED-WEAK"?c.encrePale:c.encreDouce}>
        {LABELS[item.stage] ?? item.stage}
      </T>
    </View>
    <View style={{flexDirection:"row",gap:8,marginTop:espace.m}}>
      <Stat titre="TRADES" valeur={b.trades ?? 0} compact/>
      <Stat titre="PF" valeur={pf ? pf.toFixed(2) : "—"} compact/>
      <Stat titre="WIN %" valeur={win ? `${win.toFixed(1)}` : "—"} compact/>
      <Stat titre="FWD PF" valeur={fwd ? fwd.toFixed(2) : "—"} compact/>
    </View>
    <View style={{marginTop:espace.m}}>
      <View style={{flexDirection:"row",justifyContent:"space-between"}}>
        <T v="legende">PROFIT SIMULÉ</T>
        <T v="legende">{num(b.profit).toFixed(2)} €</T>
      </View>
      <MiniCurve values={[num(b.profit)]}/>
    </View>
    <T v="petit" style={{marginTop:espace.s}}>
      {item.reason || "Résultat enregistré dans le carnet."}
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
    try {
      const [s,x]=await Promise.all([labStatus(),labStrategies(50)]);
      setStatus(s); setItems(x);
    } catch {}
  },[]);

  React.useEffect(()=>{
    charger();
    const id=setInterval(charger,5000);
    return()=>clearInterval(id);
  },[charger]);

  const refresh=async()=>{setRefreshing(true);await charger();setRefreshing(false);};
  const stage=status?.stage ?? "IDLE";
  const last=items[0];
  const running=!["IDLE","VALIDATED","ARCHIVED-WEAK","RETIRED-WEAK","ERROR"].includes(stage);
  const pfItems=items.filter(x=>num(x.backtest?.profit_factor)>0);
  const winItems=items.filter(x=>num(x.backtest?.win_rate)>0);
  const avgPf=pfItems.length ? pfItems.reduce((s,x)=>s+num(x.backtest?.profit_factor),0)/pfItems.length : 0;
  const avgWin=winItems.length ? winItems.reduce((s,x)=>s+num(x.backtest?.win_rate),0)/winItems.length : 0;
  const validated=items.filter(x=>x.stage==="VALIDATED").length;
  const candidates=items.filter(x=>["CANDIDATE","FORWARD_TEST","INCUBATION"].includes(x.stage)).length;

  return <ScrollView style={{backgroundColor:c.fond}}
    contentContainerStyle={{padding:espace.l,paddingTop:marges.top+espace.m,paddingBottom:marges.bottom+espace.xxl}}
    refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh}/>}>

    <EnTete titre="Laboratoire" sousTitre="La fabrique de stratégies — 100 % simulation, aucune exécution réelle"/>

    <Carte accent style={{marginBottom:espace.m}}>
      <View style={{flexDirection:"row",alignItems:"center"}}>
        <Pulse active={running}/>
        <T v="etiquette">{running ? "LABORATOIRE EN DIRECT" : "LABORATOIRE EN VEILLE"}</T>
        <View style={{flex:1}}/>
        <T v="legende">{status?.updated_at ? new Date(status.updated_at).toLocaleTimeString() : "—"}</T>
      </View>
      <T v="titre" style={{marginTop:6}}>{LABELS[stage] ?? stage}</T>
      <T v="petit" style={{marginTop:4}}>{status?.detail ?? "Le moteur n'a pas encore publié son état."}</T>
      <View style={{marginTop:espace.l}}><Pipeline stage={stage}/></View>
    </Carte>

    <View style={{flexDirection:"row",gap:8,marginBottom:espace.m}}>
      <Stat titre="TESTS" valeur={status?.completed ?? 0}/>
      <Stat titre="CANDIDATS" valeur={status?.candidates ?? candidates}/>
      <Stat titre="VALIDÉES" valeur={status?.validated ?? validated}/>
    </View>

    <Carte style={{marginBottom:espace.m}}>
      <T v="etiquette">CONSOLE EN DIRECT</T>
      <View style={{flexDirection:"row",alignItems:"center",marginTop:espace.m}}>
        <View style={{width:8,height:8,borderRadius:4,backgroundColor:c.jaune,marginRight:8}}/>
        <T v="corps">{status?.detail ?? "En attente du prochain cycle…"}</T>
      </View>
      <View style={{flexDirection:"row",gap:8,marginTop:espace.m}}>
        <Stat titre="PF MOYEN" valeur={avgPf ? avgPf.toFixed(2) : "—"} compact/>
        <Stat titre="WIN MOY." valeur={avgWin ? `${avgWin.toFixed(1)} %` : "—"} compact/>
        <Stat titre="CARNET" valeur={items.length} compact/>
      </View>
      {last ? <T v="legende" style={{marginTop:espace.s}}>Dernière expérience : {last.strategy_id} · {LABELS[last.stage] ?? last.stage}</T> : null}
    </Carte>

    <T v="etiquette" style={{marginBottom:espace.m}}>TABLEAU DE BORD</T>
    <Carte style={{marginBottom:espace.m}}>
      <View style={{flexDirection:"row",justifyContent:"space-between",alignItems:"flex-end"}}>
        <View>
          <T v="sousTitre">Flux d'expériences</T>
          <T v="petit" style={{marginTop:2}}>Chaque cycle est backtesté, filtré puis éventuellement envoyé en forward test.</T>
        </View>
        <T v="etiquette">{items.length} EXP.</T>
      </View>
      <View style={{marginTop:espace.l}}>
        <T v="legende" style={{marginBottom:espace.s}}>RÉSULTAT DES 8 DERNIÈRES EXPÉRIENCES</T>
        <MiniCurve values={items.slice(0,8).reverse().map(x=>num(x.backtest?.profit))}/>
        {items.slice(0,8).map((x,i)=><View key={x.strategy_id} style={{flexDirection:"row",alignItems:"center",paddingVertical:8,borderTopWidth:i?0:0,borderColor:c.filetDoux}}>
          <View style={{width:24,alignItems:"center"}}><T v="legende">{String(i+1).padStart(2,"0")}</T></View>
          <View style={{width:8,height:8,borderRadius:4,backgroundColor:x.stage==="VALIDATED"?c.gain:x.stage==="RETIRED-WEAK"?c.encrePale:c.jaune,marginHorizontal:8}}/>
          <View style={{flex:1}}><T v="petit" numberOfLines={1}>{x.strategy_id}</T></View>
          <T v="legende">PF {num(x.backtest?.profit_factor).toFixed(2)}</T>
        </View>)}
        {!items.length?<T v="legende">Le carnet se remplit au fil des cycles.</T>:null}
      </View>
    </Carte>

    <T v="etiquette" style={{marginBottom:espace.m}}>CARNET DES STRATÉGIES</T>
    {items.length ? items.map(x=><Ligne key={x.strategy_id} item={x}/>) :
      <Vide titre="Aucune stratégie enregistrée" detail="Le laboratoire commencera à remplir le carnet dès que son service sera lancé."/>}

    <Carte style={{marginTop:espace.s}}>
      <T v="etiquette">RÈGLES DU LABO</T>
      <T v="petit" style={{marginTop:espace.s}}>
        Minimum 100 trades · PF ≥ 1,20 · win rate ≥ 40 % · payoff &gt; 1 · backtest séparé du forward test.
        Une stratégie validée reste en incubation/paper et n'est jamais branchée automatiquement au compte réel.
      </T>
    </Carte>
  </ScrollView>;
}
