import re
from typing import Union, Optional

# Exclusion keywords targeting non-card merchandise, breaks, sealed boxes, reprints, and lots.
# Note: Lone words like 'box' or 'case' are intentionally NOT included to allow valid
# singles from "Mega Box", "Blaster Box", or "Case Hit" inserts.
EXCLUSION_KEYWORDS = [
    r'\blot\b',
    r'\breprint\b',
    r'\brp\b',
    r'\bfake\b',
    r'\bcustom\s*(?:card)?\b',
    r'\bproxy\b',
    r'\bdigital\b',
    r'\btopps\s*bunt\b',
    r'\bsealed\s*(?:pack|box|case)\b',
    r'\b(?:case|box|pack)\s*break\b',
    r'\bbreak\s*spot\b',
    r'\bpick\s*your\s*team\b',
    r'\bpyt\b',
    r'\brepack\b',
    r'\bmystery\s*pack\b',
    r'\bread\s+desc\b',
    r'\bempty\s*(?:box|tin|wrapper|pack)\b',
]

GRADING_COMPANIES = ["PSA", "BGS", "SGC", "CGC", "CSG", "BECKETT", "TAG", "AGS"]
COMMON_SUFFIXES = {"jr", "jr.", "sr", "sr.", "ii", "iii", "iv", "v"}

COMPETING_MANUFACTURERS = {
    "topps": {"donruss", "panini", "upper deck", "fleer", "score", "leaf", "skybox", "pacific", "press pass", "sage"},
    "bowman": {"donruss", "panini", "upper deck", "fleer", "score", "leaf", "skybox", "pacific", "press pass", "sage"},
    "panini": {"topps", "upper deck", "fleer", "bowman", "skybox", "pacific"},
    "donruss": {"topps", "upper deck", "fleer", "bowman"},
    "upper deck": {"topps", "panini", "donruss", "bowman", "score", "leaf"},
    "fleer": {"topps", "panini", "donruss", "bowman", "upper deck"},
    "score": {"topps", "upper deck", "fleer", "bowman"}
}

PARALLEL_MODIFIERS_REGEX = re.compile(
    r'(?i)\b(autographed|autograph|auto|relics?|patch(?:es)?|jersey|materials?|memorabilia|'
    r'refractors?|xfractors?|superfractors?|holofoils?|foils?|'
    r'printing\s*plates?|sepia|shimmer|cracked\s*ice|camo|pulsar|wave|'
    r'special\s*edition|'
    r'red|blue|green|gold|black|orange|purple|yellow|pink|white|silver|bronze|platinum|emerald|ruby|sapphire)\b'
)


def extract_core_series_name(series_name: str) -> str:
    """
    Strips parallel and insert modifiers from a series name to recover the base set name.
    e.g. '2006 Topps Triple Threads Autographed Relic Red' -> '2006 Topps Triple Threads'
    """
    if not series_name:
        return ""
    cleaned = PARALLEL_MODIFIERS_REGEX.sub("", series_name)
    cleaned = re.sub(r'[/–\-]+\s*$', '', cleaned)
    cleaned = " ".join(cleaned.split())
    return cleaned if len(cleaned) >= 4 else series_name



def extract_player_name_parts(player_name: str) -> dict:
    """
    Extracts first name, last name (family surname), and suffix (e.g. Jr., III).
    Correctly handles suffixes so that 'Ken Griffey Jr.' resolves to surname 'Griffey'.
    """
    cleaned = re.sub(r'[^\w\s.]', '', player_name).strip()
    tokens = cleaned.split()

    if not tokens:
        return {"first": "", "last": "", "suffix": "", "full": ""}

    if len(tokens) == 1:
        return {"first": tokens[0], "last": tokens[0], "suffix": "", "full": cleaned}

    suffix = ""
    if tokens[-1].lower() in COMMON_SUFFIXES:
        suffix = tokens[-1]
        tokens = tokens[:-1]

    # Handle compound surnames (e.g. "De La Cruz", "deGrom", "VanMeter")
    if len(tokens) >= 4 and tokens[-3].lower() == "de" and tokens[-2].lower() == "la":
        last = " ".join(tokens[-3:])
        first = " ".join(tokens[:-3])
    elif len(tokens) >= 3 and tokens[-2].lower() in {"de", "la", "van", "del", "dos", "st", "st."}:
        last = " ".join(tokens[-2:])
        first = " ".join(tokens[:-2])
    else:
        last = tokens[-1]
        first = " ".join(tokens[:-1])

    return {
        "first": first,
        "last": last,
        "suffix": suffix,
        "full": cleaned
    }


def clean_card_number(card_number: Union[str, int]) -> str:
    """
    Strips leading hash, prefix symbols (No., Card, #), and whitespace.
    """
    s = str(card_number).strip()
    s = re.sub(r'^(?:no\.?|card|#|\s)+', '', s, flags=re.IGNORECASE).strip()
    return s


def build_search_query(metadata: dict, player_name: str, card_number: str, tier: int = 1) -> str:
    """
    Constructs an optimized query with progressive relaxation across tiers.
    Removes redundant duplicate terms (e.g. manufacturer name already inside series name).

    Tier 1 (Strict)  : Year + Series + Parallel (if any) + Player + Card Number
    Tier 2 (Standard): Year + Series + Player + Card Number (drops parallel)
    Tier 3 (Relaxed) : Series + Player + Card Number (drops year prefix if redundant)
    Tier 4 (Broad)   : Player + Card Number (essential identifiers)
    """
    year_str = str(metadata.get("series_year") or "").strip()
    series = (metadata.get("series_name") or "").strip()
    mfg = (metadata.get("manufacturer_name") or "").strip()
    parallel = (metadata.get("parallel_name") or "").strip()
    clean_num = clean_card_number(card_number)

    # Clean up series name if manufacturer is already part of it
    series_clean = series
    if mfg and mfg.lower() in series_clean.lower():
        # Manufacturer already included in series name
        pass
    elif mfg:
        series_clean = f"{mfg} {series_clean}".strip()

    # Deduplicate year if already in series
    if year_str and series_clean.startswith(year_str):
        combined_set = series_clean
    elif year_str:
        combined_set = f"{year_str} {series_clean}".strip()
    else:
        combined_set = series_clean

    clean_player = re.sub(r'[/&,]+', ' ', player_name)
    clean_player = " ".join(clean_player.split())

    if tier == 1:
        tokens = [combined_set]
        if parallel:
            tokens.append(parallel)
        tokens.extend([clean_player, clean_num])
    elif tier == 2:
        tokens = [combined_set, clean_player, clean_num]
    elif tier == 3:
        # Just series name, player, and card number (or numeric part)
        num_digits = "".join(filter(str.isdigit, clean_num)) or clean_num
        tokens = [series_clean, clean_player, num_digits]
    else:
        # Tier 4: Broadest query
        num_digits = "".join(filter(str.isdigit, clean_num)) or clean_num
        tokens = [clean_player, num_digits]

    # Deduplicate whitespace and return
    query = " ".join(" ".join(t.strip() for t in tokens if t.strip()).split())
    return query


def generate_query_candidates(metadata: dict, player_name: str, card_number: str) -> list[str]:
    """
    Generates a list of fallback queries ordered from most specific to broadest,
    ensuring no exact duplicates are queried. Handles multi-player cards.
    """
    candidates = []
    for tier in [1, 2, 3, 4]:
        q = build_search_query(metadata, player_name, card_number, tier=tier)
        if q and q not in candidates:
            candidates.append(q)

    # If the series name includes parallel/insert modifiers, also generate core base-set queries
    orig_series = (metadata.get("series_name") or "").strip()
    core_series = extract_core_series_name(orig_series)
    if core_series and core_series.lower() != orig_series.lower():
        core_meta = dict(metadata)
        core_meta["series_name"] = core_series
        core_q2 = build_search_query(core_meta, player_name, card_number, tier=2)
        if core_q2 and core_q2 not in candidates:
            candidates.insert(1, core_q2)
        core_q3 = build_search_query(core_meta, player_name, card_number, tier=3)
        if core_q3 and core_q3 not in candidates:
            candidates.insert(2, core_q3)

    # For multi-player cards (e.g. "Brock Faber / Jared Spurgeon"), add surname pairs and individual players
    raw_sub_players = [p.strip() for p in re.split(r'[/&,]|\band\b', player_name) if p.strip()]
    if len(raw_sub_players) > 1:
        surnames = [extract_player_name_parts(p)["last"] for p in raw_sub_players if p]
        surnames = [s for s in surnames if s]
        series = (metadata.get("series_name") or "").strip()
        clean_num = clean_card_number(card_number)

        if len(surnames) >= 2:
            duo_query = f"{series} {' '.join(surnames)} {clean_num}"
            if duo_query not in candidates:
                candidates.append(duo_query)

        for p in raw_sub_players:
            p_q = f"{series} {p} {clean_num}"
            if p_q not in candidates:
                candidates.append(p_q)

    # Also add candidates with hyphens stripped if card_number has hyphens (e.g., TTR-48 -> TTR48)
    clean_num = clean_card_number(card_number)
    if "-" in clean_num:
        alt_num = clean_num.replace("-", "")
        for q in list(candidates):
            q_alt = q.replace(clean_num, alt_num)
            if q_alt not in candidates:
                candidates.append(q_alt)

    return candidates


def verify_listing_title(
    title: str,
    player_name: str,
    card_number: str,
    series_name: Optional[str] = None,
    manufacturer_name: Optional[str] = None,
    parallel_name: Optional[str] = None,
    relaxed: bool = False
) -> bool:
    """
    Verifies that a listing title corresponds to the target card.
    - Accurately checks the player's surname, supporting multi-player duos and quads.
    - Filters out sealed product, breaks, reprints, and competitor manufacturer cross-matches.
    - Prevents card number collisions (e.g. #243 cannot match #TTR-48).
    - Verifies series distinctive keywords when provided.
    """
    title_lower = title.lower()

    # 1. Reject junk, reprints, packs, breaks, and sealed lots
    for pattern in EXCLUSION_KEYWORDS:
        if re.search(pattern, title_lower):
            return False

    # 2. Match player surname (Mandatory, supports multi-player cards)
    raw_sub_players = [p.strip() for p in re.split(r'[/&,]|\band\b', player_name) if p.strip()]
    surnames = [extract_player_name_parts(p)["last"].lower() for p in raw_sub_players if p]
    surnames = [s for s in surnames if s]

    if surnames:
        # At least one player's surname must match the listing
        matched_player = any(re.search(rf'\b{re.escape(s)}\b', title_lower) for s in surnames)
        if not matched_player:
            return False

    # 3. Check for Manufacturer Conflicts
    if manufacturer_name:
        mfg_lower = manufacturer_name.lower().strip()
        competing = COMPETING_MANUFACTURERS.get(mfg_lower, set())
        for comp in competing:
            if re.search(rf'\b{re.escape(comp)}\b', title_lower):
                return False

    # 4. Card Number Verification & Conflict Detection
    clean_num = clean_card_number(card_number)
    num_digits = "".join(filter(str.isdigit, clean_num))
    clean_lower = clean_num.lower()

    # Match target card number with boundary anchors (e.g. '#TTR-48', '#48', 'No. 48', 'Card 48')
    escaped_num = re.escape(clean_lower)
    num_pattern = rf'(?:#|no\.?\s*|card\s*|\b){escaped_num}\b'

    has_card_num = bool(re.search(num_pattern, title_lower))
    if not has_card_num and "-" in clean_lower:
        # Also try without hyphen: 'ttr48'
        no_hyphen = clean_lower.replace("-", "")
        has_card_num = bool(re.search(rf'(?:#|no\.?\s*|card\s*|\b){re.escape(no_hyphen)}\b', title_lower))

    if not has_card_num and num_digits:
        escaped_digits = re.escape(num_digits)
        digit_pattern = rf'(?:#|no\.?\s*|card\s*|\b){escaped_digits}\b'
        has_card_num = bool(re.search(digit_pattern, title_lower))

    # Reject explicit conflicting card numbers (e.g., target is #TTR-48, but title says '#243' or '#450')
    found_hash_nums = re.findall(r'#\s*([a-zA-Z0-9-]+)', title)
    if found_hash_nums and clean_num:
        matches_any_found = any(
            fn.lower() == clean_lower or
            fn.lower().replace("-", "") == clean_lower.replace("-", "") or
            (num_digits and "".join(filter(str.isdigit, fn)) == num_digits)
            for fn in found_hash_nums
        )
        if not matches_any_found:
            return False

    # If strict and number exists, require card number match
    if not relaxed and clean_num and not has_card_num:
        return False

    # 5. Distinctive Series Keyword Verification
    if series_name:
        series_clean = series_name.lower()
        # Remove year, manufacturer, and generic card words
        for stop in ["200", "199", "198", "197", "196", "195", "relic", "card", "series", "baseball", "football", "basketball", "hockey"]:
            series_clean = re.sub(rf'\b{stop}\w*\b', '', series_clean)
        if manufacturer_name:
            series_clean = re.sub(rf'\b{re.escape(manufacturer_name.lower())}\b', '', series_clean)
        # Strip parallel/insert modifier words so generic attributes (e.g. "red", "gold") are not treated as distinctive set tokens
        series_clean = PARALLEL_MODIFIERS_REGEX.sub('', series_clean)

        distinctive = [w for w in series_clean.split() if len(w) >= 3]
        # If series has strong distinctive tokens (e.g. "triple", "threads", "chrome", "heritage", "prizm", "optic", "finest")
        # Ensure at least one distinctive set token appears in the listing title
        if distinctive and not any(w in title_lower for w in distinctive):
            return False

    # 6. Parallel match check (if parallel is requested and non-relaxed)
    if parallel_name and not relaxed:
        if parallel_name.lower() not in title_lower:
            return False

    return True


def is_graded(title: str) -> bool:
    """
    Identifies whether a title indicates a graded slab (PSA, BGS, SGC, CGC, etc.).
    Uses regex word boundaries and grading patterns.
    """
    title_upper = title.upper()
    # Check company names as standalone words
    for company in GRADING_COMPANIES:
        if re.search(rf'\b{company}\b', title_upper):
            return True

    # Check common grade notation like 'GRADE 10', 'GEM MINT 10', 'PRISTINE 10'
    if re.search(r'\b(?:GEM\s*MINT|PRISTINE|GRADED)\b', title_upper):
        return True

    return False
