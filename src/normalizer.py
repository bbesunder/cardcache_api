import re

EXCLUSION_KEYWORDS = [
    r'\blot\b', r'\breprint\b', r'\brp\b', r'\bfake\b', r'\bcustom\b',
    r'\bdigital\b', r'\bpack\b', r'\bbox\b', r'\bcase\b', r'\bbreak\b',
    r'\bread\s+desc\b', r'\bpatch\b(?=.*no\s*auto)'
]

GRADING_COMPANIES = ["PSA", "BGS", "SGC", "CGC", "CSG"]


def build_search_query(metadata: dict, player_name: str, card_number: str) -> str:
    """
    Builds a clean search query. Omits complex alphanumeric prefixes 
    if they tend to block listings where sellers omit them.
    """
    tokens = []

    year_str = str(metadata.get("series_year") or "").strip()
    series = (metadata.get("series_name") or "").strip()
    mfg = (metadata.get("manufacturer_name") or "").strip()

    if year_str and not series.startswith(year_str):
        tokens.append(year_str)

    if mfg and mfg.lower() not in series.lower():
        tokens.append(mfg)
        
    if series:
        tokens.append(series)

    if metadata.get("parallel_name"):
        tokens.append(metadata["parallel_name"])

    tokens.append(player_name)

    # Clean card number: if it has a heavy prefix like "TTR-48", 
    # just use the digits "48" or omit the prefix so eBay matches more titles.
    clean_num = str(card_number).strip().lstrip("#")
    if "-" in clean_num:
        # e.g., "TTR-48" -> try just "48" or keep the raw number optional
        num_digits = "".join(filter(str.isdigit, clean_num))
        if num_digits:
            tokens.append(num_digits)
    else:
        tokens.append(clean_num)

    return " ".join(tokens)


def verify_listing_title(title: str, player_name: str, card_number: str, parallel_name: str | None = None) -> bool:
    """
    Verifies listing titles, making the card number check optional 
    so listings missing subset codes (like 'TTR-48') are still captured.
    """
    title_lower = title.lower()

    # 1. Reject junk, reprints, packs, breaks, and lots
    for pattern in EXCLUSION_KEYWORDS:
        if re.search(pattern, title_lower):
            return False

    # 2. Match player surname (Mandatory)
    surname = player_name.split()[-1].lower()
    if surname not in title_lower:
        return False

    # 3. Optional Card Number / Digits check
    clean_num = str(card_number).strip().lstrip("#")
    num_digits = "".join(filter(str.isdigit, clean_num))
    
    # If a card number or digits exist, check if either the full number or just digits are present.
    # If neither is in the title, we still allow it through IF the player and set match 
    # (trusting eBay's search relevance for "fewer words" matches).
    has_card_num = (clean_num.lower() in title_lower) or (num_digits and num_digits in title_lower)

    # 4. Parallel match check if applicable
    if parallel_name and parallel_name.lower() not in title_lower:
        # If parallel name is missing but player/digits match, we can optionally relax it 
        # or keep it strict depending on how unique the parallel is.
        pass

    return True



def is_graded(title: str) -> bool:
    """
    Identifies whether a title indicates a graded slab.
    """
    title_upper = title.upper()
    return any(slab in title_upper for slab in GRADING_COMPANIES)