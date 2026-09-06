"""Garde-fous éditoriaux et de conformité.

Trois raisons très concrètes d'avoir ce module :
  1. Monétisation — Instagram et TikTok démonétisent le contenu suggestif ;
     un compte "borderline" ne touche ni Creator Rewards ni deals de marque.
  2. Légal — divulgation IA obligatoire (FTC US, AI Act art. 50 UE, règles
     AIGC de Meta et TikTok) et interdiction des allégations santé.
  3. Survie du compte — un shadowban efface des mois de travail.

Le module est un *gate* : rien ne part en publication sans passer par
`review_post()`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from eve.persona.persona import Persona

MIN_AGE = 18

# --- interdits durs sur les prompts image/vidéo -----------------------------
BLOCKED_VISUAL_TERMS = [
    "nude", "naked", "topless", "nsfw", "erotic", "porn", "lingerie",
    "underwear", "seductive", "sensual", "provocative", "suggestive pose",
    "wet t-shirt", "cleavage focus", "spread legs", "bedroom eyes",
    "teen", "teenager", "schoolgirl", "child", "kid", "loli", "petite girl",
    "barely legal", "young girl",
]

# Ressemblance à une personne réelle / marque : risque droit à l'image et
# contrefaçon. Liste extensible côté projet.
BLOCKED_LIKENESS = ["celebrity", "lookalike of", "resembling ", "deepfake"]

# Attribution du train de vie à un gain financier. C'est LA règle qui sépare
# un compte lifestyle d'un faux témoignage : Eve n'existe pas, elle n'a aucun
# revenu, son décor ne peut donc rien prouver.
LIFESTYLE_ATTRIBUTION_PATTERNS = [
    r"\bgr[âa]ce (à|a) (mon|le|ce) (robot|syst[èe]me|algo|bot|trading)\b",
    r"\b(mon|le|ce) (robot|syst[èe]me|algo|bot) (m'a|ma|m a) (pay|offert|permis|rendu)",
    r"\bje (gagne|me fais|touche) \d",
    r"\b(tout )?[çc]a,? c'est (le|mon) (robot|trading|syst[èe]me)\b",
    r"\bthanks to (my|the) (bot|system|algo)\b",
    r"\b(paid for by|funded by) (my|the) (bot|trading)\b",
    r"\bma vie (a chang|change) gr[âa]ce\b",
]

# Sollicitation autour d'un produit financier : hors sujet pour ce compte.
FINANCIAL_SOLICITATION_PATTERNS = [
    r"\b(rejoins|rejoignez|inscris-toi|inscrivez-vous) .{0,30}(groupe|canal|signaux|telegram|discord)\b",
    r"\b(dm|mp|message priv[ée]) pour (?:recevoir |obtenir |avoir )?(?:le |la |mon |ma |les )?"
    r"(robot|syst[èe]me|algo|acc[èe]s|signaux)\b",
    r"\bplaces? limit[ée]es?\b",
    r"\b(copie|copiez) mes (trades|positions)\b",
    r"\bcapital garanti\b",
]

# Chiffres de performance : uniquement via data/trading/results.json.
PERFORMANCE_FIGURE_PATTERN = r"([+-]?\d+[\.,]?\d*)\s?%\s?(de |en )?(rendement|profit|gain|retour|par mois|mensuel)"

# --- interdits durs sur les textes ----------------------------------------
MEDICAL_CLAIM_PATTERNS = [
    r"\bcure[sd]?\b", r"\bheals?\b", r"\btreats?\b", r"\bdiagnos",
    r"\bguérit\b", r"\bsoigne\b", r"\btraite\b",
    r"\bprevents? (cancer|diabetes|disease)\b",
    r"\bboost(s|ed)? your metabolism by\b",
    r"\bdetox(es|ing)?\b", r"\bfat[- ]burning pill\b",
    r"\bmedical advice\b", r"\bsubstitute for (a )?doctor\b",
]

GUARANTEE_PATTERNS = [
    r"\bguarantee\w*\b", r"\bgaranti\w*\b",
    r"\blose \d+\s?(kg|lbs|pounds|kilos)\b",
    r"\bperdez? \d+\s?(kg|kilos)\b",
    r"\bin (just )?\d+ days? you will\b",
    r"\brésultats? garantis?\b",
    r"\bburn \d{3,} calories\b",
]

BODY_SHAMING_PATTERNS = [
    r"\bfat\s+and\s+lazy\b", r"\bugly body\b", r"\byou should be ashamed\b",
    r"\bbikini body\b", r"\bsummer body or nothing\b", r"\bcorps parfait obligatoire\b",
]

# Contenu qui exige explicitement le disclaimer santé.
DISCLAIMER_REQUIRED_PILLARS = {"work"}


@dataclass
class ReviewResult:
    ok: bool
    blocking: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    fixed: list[str] = field(default_factory=list)

    def merge(self, other: "ReviewResult") -> "ReviewResult":
        return ReviewResult(
            ok=self.ok and other.ok,
            blocking=self.blocking + other.blocking,
            warnings=self.warnings + other.warnings,
            fixed=self.fixed + other.fixed,
        )

    def report(self) -> str:
        lines = [f"{'PASS' if self.ok else 'BLOCK'}"]
        lines += [f"  ✗ {b}" for b in self.blocking]
        lines += [f"  ⚠ {w}" for w in self.warnings]
        lines += [f"  ✎ {f}" for f in self.fixed]
        return "\n".join(lines)


class PolicyError(RuntimeError):
    """Levée quand un contenu bloquant tente d'être publié."""


def check_persona(persona: Persona) -> ReviewResult:
    res = ReviewResult(ok=True)
    if persona.age < MIN_AGE:
        res.ok = False
        res.blocking.append(
            f"Le personnage doit être un adulte (>= {MIN_AGE} ans), trouvé {persona.age}."
        )
    if not persona.raw()["identity"].get("is_ai"):
        res.ok = False
        res.blocking.append("`identity.is_ai` doit rester à true : la divulgation IA est obligatoire.")
    return res


def check_visual_prompt(prompt: str) -> ReviewResult:
    res = ReviewResult(ok=True)
    low = prompt.lower()
    for term in BLOCKED_VISUAL_TERMS:
        if term in low:
            res.ok = False
            res.blocking.append(f"Prompt visuel interdit (démonétisant ou illégal) : « {term} ».")
    for term in BLOCKED_LIKENESS:
        if term in low:
            res.ok = False
            res.blocking.append(f"Ressemblance à une personne réelle interdite : « {term} ».")
    if "bikini" in low and "beach workout" not in low:
        res.warnings.append("« bikini » réduit fortement la portée et la monétisation : préférer une tenue de sport.")
    return res


def check_caption(caption: str, persona: Persona, *, pillar: str = "") -> ReviewResult:
    res = ReviewResult(ok=True)
    low = caption.lower()

    for phrase in persona.banned_phrases:
        if phrase in low:
            res.ok = False
            res.blocking.append(f"Expression bannie par le character bible : « {phrase} ».")

    for pattern in MEDICAL_CLAIM_PATTERNS:
        if re.search(pattern, low):
            res.ok = False
            res.blocking.append(f"Allégation santé interdite (motif : {pattern}).")

    for pattern in GUARANTEE_PATTERNS:
        if re.search(pattern, low):
            res.ok = False
            res.blocking.append(f"Promesse de résultat interdite (motif : {pattern}).")

    for pattern in BODY_SHAMING_PATTERNS:
        if re.search(pattern, low):
            res.ok = False
            res.blocking.append(f"Formulation culpabilisante interdite (motif : {pattern}).")

    for pattern in LIFESTYLE_ATTRIBUTION_PATTERNS:
        if re.search(pattern, low):
            res.ok = False
            res.blocking.append(
                "Le train de vie ne peut pas être présenté comme le produit d'un gain "
                f"financier : le personnage est généré, il n'a aucun revenu (motif : {pattern}).")

    for pattern in FINANCIAL_SOLICITATION_PATTERNS:
        if re.search(pattern, low):
            res.ok = False
            res.blocking.append(f"Sollicitation autour d'un produit financier interdite (motif : {pattern}).")

    if re.search(PERFORMANCE_FIGURE_PATTERN, low) and not _figures_autorisees(caption):
        res.ok = False
        res.blocking.append(
            "Chiffre de performance sans les mentions obligatoires. Un post chiffré doit "
            "citer le drawdown, la période, et rappeler « résultats passés / pas un conseil ». "
            "Les chiffres doivent venir de data/trading/results.json.")

    tag = persona.disclosure["caption_tag"].lower()
    ai_hashtags = [h.lower() for h in persona.disclosure["hashtags"]]
    has_disclosure = tag in low or any(h in low for h in ai_hashtags)
    if not has_disclosure:
        res.ok = False
        res.blocking.append("Divulgation IA absente de la légende (obligatoire : FTC / AI Act / Meta / TikTok).")

    if pillar in DISCLAIMER_REQUIRED_PILLARS:
        markers = ("pas un conseil", "not investment advice", "résultats passés",
                   "past performance", "perte en capital", "risque")
        if not any(m in low for m in markers):
            res.warnings.append(
                "Avertissement de risque recommandé dès qu'on parle du système.")

    if len(caption) > 2200:
        res.ok = False
        res.blocking.append("Légende > 2200 caractères : rejetée par Instagram.")

    return res


def _figures_autorisees(caption: str) -> bool:
    """Un chiffre de performance n'est publiable qu'entouré de son contexte."""
    low = caption.lower()
    a_le_risque = "drawdown" in low or "perte en capital" in low
    a_le_cadre = ("résultats passés" in low or "past performance" in low
                  or "pas un conseil" in low or "not investment advice" in low)
    return a_le_risque and a_le_cadre


def ensure_disclosure(caption: str, persona: Persona) -> tuple[str, list[str]]:
    """Ajoute la mention IA si elle manque. Retourne (légende, corrections)."""
    fixed: list[str] = []
    low = caption.lower()
    tag = persona.disclosure["caption_tag"]
    hashtags = persona.disclosure["hashtags"]
    if tag.lower() not in low and not any(h.lower() in low for h in hashtags):
        caption = f"{caption.rstrip()}\n\n{tag} {' '.join(hashtags)}"
        fixed.append("Mention de divulgation IA ajoutée automatiquement.")
    return caption, fixed


def review_post(
    persona: Persona,
    *,
    caption: str,
    visual_prompts: list[str] | None = None,
    pillar: str = "",
    autofix: bool = True,
) -> tuple[str, ReviewResult]:
    """Point d'entrée unique avant publication.

    Corrige ce qui est corrigeable (divulgation), bloque le reste.
    """
    result = check_persona(persona)
    if autofix:
        caption, fixed = ensure_disclosure(caption, persona)
        result.fixed.extend(fixed)

    result = result.merge(check_caption(caption, persona, pillar=pillar))
    for prompt in visual_prompts or []:
        result = result.merge(check_visual_prompt(prompt))
    return caption, result


def enforce(result: ReviewResult) -> None:
    if not result.ok:
        raise PolicyError("Publication bloquée :\n" + "\n".join(f"- {b}" for b in result.blocking))
