"""Name normalisation and variants used for matching institution names against the official lists."""
from __future__ import annotations

import re

# Well-known, unambiguous abbreviations → official names (offline; the OpenAI resolver covers everything else).
# Two-letter forms (AU, MU, DU…) are deliberately absent: each stands for several universities.
ABBREVIATIONS = {
    "VTU": "Visvesvaraya Technological University",
    "AKTU": "Dr. A.P.J. Abdul Kalam Technical University",
    "IGNOU": "Indira Gandhi National Open University",
    "GTU": "Gujarat Technological University",
    "RGPV": "Rajiv Gandhi Proudyogiki Vishwavidyalaya",
    "SPPU": "Savitribai Phule Pune University",
    "MAKAUT": "Maulana Abul Kalam Azad University of Technology",
    "BPUT": "Biju Patnaik University of Technology",
    "RTU": "Rajasthan Technical University",
    "KTU": "A.P.J. Abdul Kalam Technological University",
    "JNTU": "Jawaharlal Nehru Technological University",
    "JNTUH": "Jawaharlal Nehru Technological University",
    "JNTUK": "Jawaharlal Nehru Technological University (Kainada)",      # UGC's spelling
    "JNTUA": "Jawaharlal Nehru Technological University (Anantapur)",
    "JNU": "Jawaharlal Nehru University",
    "BHU": "Banaras Hindu University",
    "AMU": "Aligarh Muslim University",
    "CSJMU": "Chhatrapati Shahu Ji Maharaj University",
    "RTMNU": "Rashtrasant Tukadoji Maharaj Nagpur University",
    "MDU": "Maharshi Dayanand University",
    "KUK": "Kurukshetra University",
    "GGSIPU": "Guru Gobind Singh Indraprastha University",
    "IPU": "Guru Gobind Singh Indraprastha University",
    "DTU": "Delhi Technological University",
    "NSUT": "Netaji Subhas University of Technology",
    "PTU": "I.K. Gujral Punjab Technical University",
    "IKGPTU": "I.K. Gujral Punjab Technical University",
    "CSVTU": "Chhattisgarh Swami Vivekanand Technical University",
    "BEU": "Bihar Engineering University",
    "SRM": "SRM Institute of Science and Technology",
    "VIT": "Vellore Institute of Technology",
    "BITS": "Birla Institute of Technology and Science",
    "MAHE": "Manipal Academy of Higher Education",
    "PRIST": "Ponnaiyah Ramajayam Institute of Science and Technology",
    "SASTRA": "Shanmugha Arts, Science, Technology & Research Academy",
    "YCMOU": "Yashwantrao Chavan Maharashtra Open University",
    "NMIMS": "SVKM's Narsee Monjee Institute of Management Studies",
    "SNDT": "S.N.D.T. Women's University",
}

# Common spelling → the spelling the official UGC list actually uses (the UGC list has a few misspellings).
OFFICIAL_SPELLINGS = {
    "VISVESVARAYA TECHNOLOGICAL UNIVERSITY": "Vesveswaraiah Technological University",
    "VISVESWARAYA TECHNOLOGICAL UNIVERSITY": "Vesveswaraiah Technological University",
    "JAWAHARLAL NEHRU TECHNOLOGICAL UNIVERSITY KAKINADA": "Jawaharlal Nehru Technological University (Kainada)",
    "JNTU KAKINADA": "Jawaharlal Nehru Technological University (Kainada)",
    "JNTU ANANTAPUR": "Jawaharlal Nehru Technological University (Anantapur)",
    "JNTU HYDERABAD": "Jawaharlal Nehru Technological University",
}

# Words that mean the same thing in official lists ("Univ." / "Vishwavidyalaya" are NOT folded: they are part of
# many official names and folding them would create false matches).
_WORD_FOLD = [
    (r"\bUNIV\b\.?", "UNIVERSITY"), (r"\bINST\b\.?", "INSTITUTE"), (r"\bTECH\b\.?", "TECHNOLOGY"),
    (r"\bENGG\b\.?", "ENGINEERING"), (r"\bCOLL\b\.?", "COLLEGE"), (r"\bGOVT\b\.?", "GOVERNMENT"),
    (r"\bSCI\b\.?", "SCIENCE"), (r"\bMGMT\b\.?", "MANAGEMENT"), (r"\bNATL\b\.?", "NATIONAL"),
    (r"\bST\b\.?", "SAINT"), (r"\bSHRI\b", "SRI"), (r"\bSHREE\b", "SRI"),
    (r"\bSREE\b", "SRI"),
]

# Words that do not identify an institution on their own ("College of Engineering", "Government Polytechnic").
GENERIC = {"UNIVERSITY", "COLLEGE", "INSTITUTE", "OF", "AND", "THE", "TECHNOLOGY", "ENGINEERING", "SCIENCE",
         "SCIENCES", "MANAGEMENT", "GOVERNMENT", "POLYTECHNIC", "SCHOOL", "STUDIES", "RESEARCH", "EDUCATION",
         "ACADEMY", "CENTRE", "CENTER", "NATIONAL", "INTERNATIONAL", "INDIAN", "INDIA", "SRI", "SAINT", "DR",
         "OPEN", "TECHNICAL", "TECHNOLOGICAL", "WOMEN", "WOMENS", "MEDICAL", "LAW", "AGRICULTURAL", "VIDYAPEETH",
         "VISHWAVIDYALAYA", "DEEMED", "BE", "TO", "FOR", "IN", "ARTS", "COMMERCE", "PHARMACY", "NEW", "OLD",
         "NORTH", "SOUTH", "EAST", "WEST", "CENTRAL", "STATE", "CITY", "RURAL", "URBAN", "DISTRICT"}


FORMER_RE = re.compile(r"\(\s*(?:formerly(?:\s+known\s+as)?|earlier(?:\s+known\s+as)?|previously(?:\s+known\s+as)?|"
                       r"old\s+name|erstwhile)\s*[:\-]?\s*([^)]+)\)", re.I)
PAREN_RE = re.compile(r"\(([^)]*)\)")
DEEMED_RE = re.compile(r"\(?\s*deemed(?:\s+to\s+be)?(?:\s+university)?\s*(?:u/s\s*3[^)]*)?\)?", re.I)


def norm(name: str | None) -> str:
    """Upper-case, '&'→AND, punctuation removed, abbreviations folded, 'THE' dropped, single spaces."""
    s = (name or "").upper().replace("&", " AND ").replace("’", "'")
    s = re.sub(r"(?<=\b[A-Z])\.(?=[A-Z]\b)", "", s)          # A.P.J. → APJ (initials)
    s = re.sub(r"(?<=\b[A-Z])\.(?=\s|$)", "", s)
    s = s.replace("'S ", "S ").replace("'", "")
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    for pat, rep in _WORD_FOLD:
        s = re.sub(pat, rep, s)
    s = re.sub(r"\bTHE\b", " ", s)
    s = re.sub(r"\b([A-Z]) (?=[A-Z]\b)", r"\1", s)            # "A P J" → "APJ"
    return re.sub(r"\s+", " ", s).strip()


def former_names(name: str) -> list[str]:
    """'X (Formerly Y)' → ['Y']."""
    return [m.strip(" .\"'") for m in FORMER_RE.findall(name or "") if len(m.strip()) > 3]


def base_name(name: str) -> str:
    """Name without former-name brackets and without a '(Deemed to be University)' tag."""
    s = FORMER_RE.sub(" ", name or "")
    s = DEEMED_RE.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip(" ,-")


def variants(name: str, place_words: set[str] | frozenset = frozenset()) -> list[str]:
    """Normalised variants of an institution name, most specific first.

    'Anna University, Chennai'          → ANNA UNIVERSITY CHENNAI, ANNA UNIVERSITY
    'University of Mumbai'              → UNIVERSITY OF MUMBAI, MUMBAI UNIVERSITY
    'XYZ (Formerly ABC University)'     → XYZ, ABC UNIVERSITY
    'VTU'                               → VTU, VISVESVARAYA TECHNOLOGICAL UNIVERSITY
    """
    raw = re.sub(r"\[.*?\]", " ", name or "")
    raw = re.sub(r"\s+-\s+(INDIA|India)\b.*$", "", raw)
    raw = re.sub(r"\s+-\s+\d{6}\b.*$", "", raw)                    # "- 600025" pin code
    raw = re.sub(r"\b\d{6}\b", " ", raw)
    out: list[str] = []

    def add(s: str):
        n = norm(s)
        # every shortened variant must keep a distinctive word: "COLLEGE OF ENGINEERING PUNE" may not become the
        # generic "COLLEGE OF ENGINEERING" (the full name, out[0], is always kept)
        if len(n) > 2 and n not in out and (not out or distinctive(n)):
            out.append(n)

    add(raw)
    b = base_name(raw)
    add(b)
    for f in former_names(raw):
        add(f)
    add(b.split(",")[0])                                            # drop ", City"
    no_paren = PAREN_RE.sub(" ", b)
    add(no_paren)
    for inner in PAREN_RE.findall(b):                               # "(PRIST)" / "(Anantapur)"
        key = norm(inner).replace(" ", "")
        if key in ABBREVIATIONS:
            add(ABBREVIATIONS[key])
    for v in list(out):
        key = v.replace(" ", "")
        if key in ABBREVIATIONS:
            add(ABBREVIATIONS[key])
    for v in list(out):
        if v in OFFICIAL_SPELLINGS:
            add(OFFICIAL_SPELLINGS[v])
        m = re.fullmatch(r"UNIVERSITY OF (.+)", v)                  # University of Mumbai ↔ Mumbai University
        if m:
            add(f"{m.group(1)} UNIVERSITY")
        m = re.fullmatch(r"(.+) UNIVERSITY", v)
        if m and " " not in m.group(1).strip():
            add(f"UNIVERSITY OF {m.group(1)}")
        if place_words:                                             # "ANNA UNIVERSITY CHENNAI" → "ANNA UNIVERSITY"
            toks = v.split()
            while len(toks) > 2 and toks[-1] in place_words:
                toks = toks[:-1]
                add(" ".join(toks))
    return out


def distinctive(normed: str) -> bool:
    return any(t not in GENERIC and not t.isdigit() for t in normed.split())


def search_term(name: str) -> str:
    """Short, distinctive text to type into the UGC site's search box ('Anna University, Chennai' → 'Anna University')."""
    s = base_name(re.sub(r"\[.*?\]", " ", name or ""))
    s = PAREN_RE.sub(" ", s).split(",")[0]
    s = re.sub(r"\s+", " ", s).strip()
    key = norm(s).replace(" ", "")
    if key in ABBREVIATIONS:
        s = ABBREVIATIONS[key]
    return s or (name or "").strip()


def website_domain(url: str | None) -> str:
    """'https://www.annauniv.edu/x' → 'annauniv.edu'."""
    s = re.sub(r"^[a-z]+://", "", (url or "").strip().lower())
    s = s.split("/")[0].split(":")[0]
    return s[4:] if s.startswith("www.") else s
