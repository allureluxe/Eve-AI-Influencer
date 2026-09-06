"""Interface en ligne de commande de l'agent Eve.

    python -m eve.cli go              # ⭐ tout faire en une commande

Les commandes ci-dessous sont les briques que `go` enchaîne pour toi :

    python -m eve.cli doctor          # diagnostic de l'installation
    python -m eve.cli preview         # un script de vidéo, sans rien produire
    python -m eve.cli plan --days 7   # calendrier éditorial
    python -m eve.cli produce --limit 2
    python -m eve.cli approve --all
    python -m eve.cli run             # cycle complet (dry-run par défaut)
    python -m eve.cli loop --hours 12 # mode autonome
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from datetime import date as Date

from eve.agent.orchestrator import EveAgent, _piece_from_row
from eve.agent.state import Store
from eve.config import settings
from eve.content.launch import build_bios, build_launch_kit
from eve.content.scripts import build_piece
from eve.media.video import ffmpeg_available
from eve.monetization.products import build_media_kit, export_guide
from eve.monetization.revenue import milestones, project_monthly, summarize, RevenueEntry
from eve.persona.persona import load_persona
from eve.safety.policy import check_persona
from eve.utils.logging import setup as setup_logging

OK, KO, WARN = "✅", "❌", "⚠️ "


def cmd_doctor(args) -> int:
    persona = load_persona()
    print(f"\n🤖 Eve — diagnostic\n{'─' * 52}")
    print(f"Personnage      : {persona.raw()['identity']['full_name']}, {persona.age} ans, "
          f"@{persona.handle}")
    review = check_persona(persona)
    print(f"Conformité      : {OK if review.ok else KO} "
          + ("personnage valide" if review.ok else "; ".join(review.blocking)))
    print(f"Mode            : {'DRY-RUN (aucune publication)' if settings.dry_run else 'PUBLICATION RÉELLE'}")
    print(f"Validation      : {'humaine requise' if settings.require_human_review else 'automatique'}")
    print(f"\nGénération\n{'─' * 52}")
    print(f"Images          : {settings.generation.image_provider} "
          f"({settings.generation.image_model})")
    print(f"Voix            : {settings.generation.voice_provider} "
          f"{OK if shutil.which('edge-tts') else WARN + 'binaire absent → piste muette'}")
    print(f"LLM             : {settings.generation.llm_provider} "
          f"{'(hors-ligne, bibliothèque locale)' if settings.generation.llm_provider == 'template' else ''}")
    print(f"ffmpeg          : {OK if ffmpeg_available() else KO + ' absent → pas de montage vidéo'}")
    print(f"\nPublication\n{'─' * 52}")
    pub = settings.publishing
    print(f"Instagram       : {OK if pub.instagram_token and pub.instagram_user_id else WARN + 'non configuré'}")
    print(f"TikTok          : {OK if pub.tiktok_access_token else WARN + 'non configuré'}")
    print(f"URL publique    : {pub.public_media_base_url or WARN + 'requise pour Instagram'}")
    print(f"Créneaux        : {', '.join(pub.time_slots)} ({pub.timezone})")
    print(f"\nMonétisation\n{'─' * 52}")
    from eve.monetization.links import build_offers
    offers = build_offers()
    print(f"Offres actives  : {', '.join(o.key for o in offers) if offers else WARN + 'aucune (voir .env)'}")
    stats = Store().stats()
    print(f"\nBase            : {stats}\n")
    return 0


def cmd_preview(args) -> int:
    persona = load_persona()
    piece = build_piece(persona, day=Date.today(), slot=args.slot, pillar=args.pillar)
    print(f"\n▶ {piece.title}  ({piece.duration_s}s · {len(piece.beats)} plans · {piece.pillar})\n")
    for b in piece.beats:
        print(f"  [{b.start_s:5.1f}s → {b.end_s:5.1f}s]  {b.voiceover}")
        print(f"        écran : {b.on_screen}")
        print(f"        image : {b.shot_prompt[:110]}…\n")
    from eve.content.captions import caption_for
    for platform in ("tiktok", "instagram"):
        print(f"── Légende {platform} " + "─" * 32)
        print(caption_for(piece, persona, platform))
        print()
    return 0


def cmd_plan(args) -> int:
    agent = EveAgent()
    pieces = agent.plan(days=args.days)
    print(f"\n{len(pieces)} contenu(s) planifié(s) :\n")
    for p in pieces:
        flag = {"blocked": KO, "approved": OK}.get(p.status, "•")
        print(f"  {flag} {p.date} {p.slot}  {p.pillar:<14} {p.title[:52]}")
    print(f"\nStatut : {'validation humaine requise' if settings.require_human_review else 'auto-approuvé'}")
    return 0


def cmd_produce(args) -> int:
    agent = EveAgent()
    store = agent.store
    rows = ([store.get_piece(args.id)] if args.id
            else store.pieces_by_status("approved", limit=args.limit)
            or store.pieces_by_status("draft", limit=args.limit))
    rows = [r for r in rows if r]
    if not rows:
        print("Rien à produire. Lance `plan` d'abord.")
        return 1
    for row in rows[:args.limit]:
        piece = _piece_from_row(row)
        print(f"⏳ Production {piece.id} ({len(piece.beats)} plans)…")
        piece = agent.produce(piece, force=args.force)
        print(f"   vidéo   : {piece.assets.get('video', KO + ' ' + piece.assets.get('video_error', ''))}")
        if piece.assets.get("warning"):
            print(f"   {WARN}{piece.assets['warning']}")
    return 0


def cmd_approve(args) -> int:
    store = Store()
    rows = store.pieces_by_status("draft", limit=200) if args.all else [store.get_piece(args.id)]
    rows = [r for r in rows if r]
    for row in rows:
        store.set_status(row["id"], "approved")
        print(f"{OK} approuvé : {row['id']}")
    if not rows:
        print("Aucun contenu en attente.")
    return 0


def cmd_publish(args) -> int:
    agent = EveAgent()
    rows = ([agent.store.get_piece(args.id)] if args.id
            else agent.store.due_pieces(Date.today().isoformat(), limit=args.limit))
    rows = [r for r in rows if r]
    if not rows:
        print("Aucun contenu prêt à publier (statut `approved` ou `ready`).")
        return 1
    for row in rows:
        piece = _piece_from_row(row)
        if not piece.assets.get("video"):
            piece = agent.produce(piece)
        for result in agent.publish(piece, platforms=args.platforms):
            print(f"  {piece.id} → {result}")
    if settings.dry_run:
        print(f"\n{WARN}DRY_RUN actif : rien n'a été réellement publié. "
              "Passe DRY_RUN=0 dans .env quand tu es prêt.")
    return 0


def cmd_run(args) -> int:
    agent = EveAgent()
    report = agent.daily_run(days_ahead=args.days, max_publish=args.max_publish)
    print(report.to_markdown(agent.persona))
    return 0


def cmd_loop(args) -> int:
    agent = EveAgent()
    interval = max(args.hours, 1) * 3600
    print(f"Mode autonome : un cycle toutes les {args.hours} h. Ctrl+C pour arrêter.")
    while True:
        report = agent.daily_run(days_ahead=args.days, max_publish=args.max_publish)
        print(report.to_markdown(agent.persona))
        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            print("\nArrêt demandé.")
            return 0


def cmd_metrics(args) -> int:
    agent = EveAgent()
    collected, weights = agent.learn()
    print(f"{collected} publication(s) mesurée(s).")
    print("Nouvelles pondérations :")
    for k, v in sorted(weights.items(), key=lambda kv: -kv[1]):
        print(f"  {k:<15} {v:.0%}")
    from eve.analytics.optimizer import recommendations
    print()
    for r in recommendations(agent.store, agent.persona):
        print(f"  • {r}")
    return 0


def cmd_product(args) -> int:
    persona = load_persona()
    paths = export_guide(persona, title=args.title)
    kit = build_media_kit(persona, {})
    print(f"{OK} Guide : {paths['markdown']}")
    print(f"{OK} Version imprimable (PDF via le navigateur) : {paths['html']}")
    print(f"{OK} Media kit : {kit}")
    return 0


def cmd_revenue(args) -> int:
    store = Store()
    if args.add:
        source, amount = args.add
        store.add_revenue(Date.today().isoformat(), source, float(amount), args.note or "")
        print(f"{OK} {amount} $ enregistrés ({source}).")
    rows = [RevenueEntry(r["day"], r["source"], r["amount_usd"], r["note"] or "")
            for r in store.revenue_rows()]
    print("\nRevenus enregistrés :", summarize(rows) if rows else "aucun")
    print("\nProjection mensuelle (fourchette prudente) :")
    for source, (low, high) in project_monthly(args.followers, args.views).items():
        print(f"  {source:<12} {low:>8.0f} $ → {high:>8.0f} $")
    print("\nProchains paliers :")
    for m in milestones(args.followers):
        print(f"  • {m}")
    return 0


def cmd_persona(args) -> int:
    persona = load_persona()
    print(json.dumps(persona.raw(), ensure_ascii=False, indent=2))
    return 0


def cmd_go(args) -> int:
    """Tout en une commande : vérifier, planifier, produire, expliquer la suite.

    C'est le point d'entrée pour qui ne veut pas apprendre le reste du CLI.
    Rien n'est publié : `go` s'exécute toujours en mode dry-run.
    """
    persona = load_persona()
    env = settings.paths.root / ".env"
    example = settings.paths.root / ".env.example"
    if not env.exists() and example.exists():
        env.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"{OK} Fichier .env créé à partir du modèle.")

    print(f"\n🤖 {persona.raw()['identity']['full_name']} — @{persona.handle}")
    print(f"   {persona.raw()['expertise']['positioning']}\n")

    manques = []
    if not ffmpeg_available():
        manques.append("ffmpeg (montage vidéo) → sudo apt install ffmpeg  /  brew install ffmpeg")
    if not shutil.which("edge-tts"):
        manques.append("edge-tts (voix off) → pip install edge-tts")
    if manques:
        print(f"{WARN}Il manque de quoi produire une vidéo complète :")
        for m in manques:
            print(f"    · {m}")
        print("   Je continue quand même avec ce qui est disponible.\n")

    agent = EveAgent(persona=persona)
    nouveaux = agent.plan(days=args.days)
    en_attente = agent.store.pieces_by_status("draft", limit=200)
    for row in en_attente:
        agent.store.set_status(row["id"], "approved")
    print(f"{OK} Calendrier : {len(nouveaux)} nouveau(x) contenu(s) sur {args.days} jours.")

    faits = []
    for row in agent.store.pieces_by_status("approved", limit=args.videos):
        piece = _piece_from_row(row)
        print(f"⏳ Production de « {piece.title} » ({len(piece.beats)} plans)…")
        piece = agent.produce(piece)
        if piece.assets.get("video"):
            faits.append(piece)
            print(f"   {OK} {piece.assets['video']}")
        else:
            print(f"   {KO} vidéo non montée : {piece.assets.get('video_error', 'cause inconnue')}")
        if piece.assets.get("warning"):
            print(f"   {WARN}{piece.assets['warning']}")

    produit = export_guide(persona)
    kit = build_media_kit(persona, {})
    lancement = build_launch_kit(persona)

    print(f"\n{'═' * 58}\n  CE QUE TU AS MAINTENANT\n{'═' * 58}")
    if faits:
        print(f"  🎬 {len(faits)} vidéo(s) dans  output/videos/")
        print("       (la légende à copier-coller est dans legendes.txt, à côté)")
    print(f"  🚀 Kit de lancement des comptes {lancement['html']}")
    print(f"  📄 Guide de style (aimant)      {produit['html']}")
    print(f"  📊 Media kit pour les marques   {kit}")
    print(f"\n{'═' * 58}\n  LA SUITE, DANS L'ORDRE\n{'═' * 58}")
    print("""  1. Regarde les vidéos produites. Si le rendu te plaît, continue.
  2. Ouvre le kit de lancement : pseudo, photo de profil, bios prêtes
     à coller, et la liste de contrôle des comptes.
  3. Publie les MP4 à la main pendant une à deux semaines. La légende
     de chaque vidéo est dans son legendes.txt — copier, coller, publier.
  4. Quand le rythme est pris : docs/SETUP.md pour connecter les API,
     puis DRY_RUN=0 dans .env pour laisser l'agent publier seul.
  5. Pour produire la suite :  python -m eve.cli go""")
    print(f"\n  Tout est en dry-run : {WARN}rien n'a été publié.\n")
    return 0


def cmd_lancement(args) -> int:
    persona = load_persona()
    kit = build_launch_kit(persona)
    bios = build_bios(persona)
    print(f"\n{OK} Kit de lancement : {kit['html']}")
    print(f"{OK} Photo de profil   : {kit['photo']}\n")
    for plateforme, bio in bios.items():
        print(f"── Bio {plateforme} " + "─" * 38)
        print(bio)
        print()
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser("eve", description="Agent autonome pour l'influenceuse IA Eve.")
    p.add_argument("--log-level", default=None)
    sub = p.add_subparsers(dest="command", required=True)

    go = sub.add_parser("go", help="⭐ tout faire en une commande (recommandé)")
    go.add_argument("--days", type=int, default=3, help="jours de contenu à planifier")
    go.add_argument("--videos", type=int, default=1, help="vidéos à produire maintenant")
    go.set_defaults(func=cmd_go)

    sub.add_parser("lancement", help="kit pour créer les comptes (bio, photo, checklist)"
                   ).set_defaults(func=cmd_lancement)

    sub.add_parser("doctor", help="diagnostic complet").set_defaults(func=cmd_doctor)

    pv = sub.add_parser("preview", help="afficher un script sans rien générer")
    pv.add_argument("--pillar", default="fashion")
    pv.add_argument("--slot", default="06:30")
    pv.set_defaults(func=cmd_preview)

    pl = sub.add_parser("plan", help="planifier le calendrier éditorial")
    pl.add_argument("--days", type=int, default=7)
    pl.set_defaults(func=cmd_plan)

    pr = sub.add_parser("produce", help="générer images, voix et vidéo")
    pr.add_argument("--id", default=None)
    pr.add_argument("--limit", type=int, default=1)
    pr.add_argument("--force", action="store_true")
    pr.set_defaults(func=cmd_produce)

    ap = sub.add_parser("approve", help="valider un contenu (revue humaine)")
    ap.add_argument("--id", default=None)
    ap.add_argument("--all", action="store_true")
    ap.set_defaults(func=cmd_approve)

    pb = sub.add_parser("publish", help="publier sur TikTok et Instagram")
    pb.add_argument("--id", default=None)
    pb.add_argument("--limit", type=int, default=2)
    pb.add_argument("--platforms", nargs="*", default=None, choices=["tiktok", "instagram"])
    pb.set_defaults(func=cmd_publish)

    rn = sub.add_parser("run", help="cycle complet : apprendre, planifier, produire, publier")
    rn.add_argument("--days", type=int, default=3)
    rn.add_argument("--max-publish", type=int, default=2)
    rn.set_defaults(func=cmd_run)

    lp = sub.add_parser("loop", help="exécution autonome en continu")
    lp.add_argument("--hours", type=int, default=12)
    lp.add_argument("--days", type=int, default=3)
    lp.add_argument("--max-publish", type=int, default=2)
    lp.set_defaults(func=cmd_loop)

    sub.add_parser("metrics", help="collecter les stats et ré-optimiser").set_defaults(func=cmd_metrics)

    pd = sub.add_parser("product", help="générer le guide de style et le media kit")
    pd.add_argument("--title", default="La garde-robe de 30 pièces")
    pd.set_defaults(func=cmd_product)

    rv = sub.add_parser("revenue", help="suivi et projection de revenus")
    rv.add_argument("--followers", type=int, default=1000)
    rv.add_argument("--views", type=int, default=50000)
    rv.add_argument("--add", nargs=2, metavar=("SOURCE", "MONTANT"), default=None)
    rv.add_argument("--note", default="")
    rv.set_defaults(func=cmd_revenue)

    sub.add_parser("persona", help="afficher le character bible").set_defaults(func=cmd_persona)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging(args.log_level)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
