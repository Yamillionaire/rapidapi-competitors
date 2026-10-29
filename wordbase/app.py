"""WordBase Dictionary - competitor to WordsAPI (dpventures) on RapidAPI.

Incumbent verified 2026-10-28: 1,561 subscribers, rated 2/5 (53 votes),
pricing $0/$10/$49/$89. Complaints in its Discussions and reviews: valid
keys rejected with 403s, Discussions abandoned and spam-filled, partial
word records with silently empty fields.
This service: the same public data the incumbent's product is built on
(Princeton WordNet 3.1, WordNet license), plus the CMU Pronouncing
Dictionary (pronunciation, syllables, rhymes) and the FrequencyWords
OpenSubtitles list (frequency, labeled a Zipf-scale estimate), served on
the shared scaffold. Every rejection is an explicit JSON error; a word
the data does not know returns a clean documented 404, never a partial
record and never a spurious 403.
Datasets download at boot when absent (GeoBase pattern): the WordNet
tarball is 16MB, too large for the repo snapshot route.
Zero dependencies beyond the shared scaffold. Run: python3 app.py (PORT env, default 8107).
"""
import io
import math
import os
import re
import sys
import tarfile
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
from rapidapi_server import run

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
WN_TARBALL = "https://wordnetcode.princeton.edu/wn3.1.dict.tar.gz"
CMU_URL = "https://raw.githubusercontent.com/cmusphinx/cmudict/master/cmudict.dict"
FREQ_URL = "https://raw.githubusercontent.com/hermitdave/FrequencyWords/master/content/2018/en/en_50k.txt"
POS_FILES = {"n": "noun", "v": "verb", "a": "adj", "r": "adv"}
POS_NAMES = {"n": "noun", "v": "verb", "a": "adjective", "s": "adjective", "r": "adverb"}


def ensure_data():
    """Load from local files when present; otherwise pull the datasets.

    WordNet's dict files are ~32MB of text, too large for the repo
    snapshot route, so the service fetches them at boot (GeoBase pattern).
    """
    wanted = ([f"data.{s}" for s in POS_FILES.values()]
              + [f"index.{s}" for s in POS_FILES.values()]
              + [f"{s}.exc" for s in POS_FILES.values()]
              + ["cmudict.dict", "en_50k.txt"])
    if all(os.path.exists(os.path.join(DATA_DIR, f)) for f in wanted):
        return
    os.makedirs(DATA_DIR, exist_ok=True)
    last_error = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(WN_TARBALL, timeout=120) as resp:
                blob = resp.read()
            with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tf:
                for name in wanted[:12]:
                    member = tf.getmember(f"dict/{name}")
                    with tf.extractfile(member) as src, open(os.path.join(DATA_DIR, name), "wb") as fh:
                        fh.write(src.read())
            for url, name in ((CMU_URL, "cmudict.dict"), (FREQ_URL, "en_50k.txt")):
                with urllib.request.urlopen(url, timeout=60) as resp:
                    payload = resp.read()
                with open(os.path.join(DATA_DIR, name), "wb") as fh:
                    fh.write(payload)
            return
        except Exception as exc:  # retry a few times, then fail loudly at boot
            last_error = exc
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"dataset download failed: {last_error}")


ensure_data()

# ---------------------------------------------------------------- WordNet
# Lemma index: normalized lemma -> [(index_pos, byte_offset)], parsed from
# index.* at boot. Synsets are parsed on demand by seeking into data.*.

lemma_index = {}
for _pos, _suffix in POS_FILES.items():
    with open(os.path.join(DATA_DIR, f"index.{_suffix}"), encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if line.startswith(" ") or not line.strip():
                continue  # license header
            parts = line.split()
            lemma, synset_cnt = parts[0], int(parts[2])
            offsets = [int(x) for x in parts[-synset_cnt:]] if synset_cnt else []
            lemma_index.setdefault(lemma.lower(), []).extend((_pos, off) for off in offsets)

_data_handles = {suffix: open(os.path.join(DATA_DIR, f"data.{suffix}"), "rb")
                 for suffix in POS_FILES.values()}
_synset_cache = {}


def parse_synset(file_pos, offset):
    """Parse one synset line from data.<file_pos> at byte offset."""
    key = (file_pos, offset)
    if key in _synset_cache:
        return _synset_cache[key]
    fh = _data_handles[POS_FILES[file_pos]]
    fh.seek(offset)
    line = fh.readline().decode("utf-8", errors="replace")
    head, _, gloss = line.partition("|")
    tokens = head.split()
    ss_type = tokens[2]
    w_cnt = int(tokens[3], 16)
    lemmas, idx = [], 4
    for i in range(w_cnt):
        lemmas.append(tokens[idx].replace("_", " "))
        idx += 2  # word, lex_id
    p_cnt = int(tokens[idx])
    idx += 1
    pointers = []
    for _ in range(p_cnt):
        symbol, target, t_pos, src_tgt = tokens[idx:idx + 4]
        pointers.append((symbol, int(target), t_pos, int(src_tgt[:2], 16), int(src_tgt[2:], 16)))
        idx += 4
    gloss = gloss.strip()
    gloss_parts = [p.strip() for p in gloss.split("; ")] if gloss else []
    definition = gloss_parts[0] if gloss_parts else ""
    examples = [p.strip('"') for p in gloss_parts[1:] if p.startswith('"')]
    parsed = {"pos": POS_NAMES.get(ss_type, ss_type), "ss_type": ss_type,
              "lemmas": lemmas, "definition": definition, "examples": examples,
              "pointers": pointers}
    if len(_synset_cache) > 40000:
        _synset_cache.clear()
    _synset_cache[key] = parsed
    return parsed


def synset_lemmas(file_pos, offset):
    try:
        return parse_synset(file_pos, offset)["lemmas"]
    except Exception:
        return []


SYNSET_RELATIONS = {  # response key -> WordNet pointer symbols (synset level)
    "typeOf": ("@", "@i"), "hasTypes": ("~", "~i"),
    "partOf": ("#p", "#m", "#s"), "hasParts": ("%p", "%m", "%s"),
    "memberOf": ("#m",), "hasMembers": ("%m",),
    "substanceOf": ("#s",), "hasSubstances": ("%s",),
    "similarTo": ("&",), "also": ("^",),
    "entails": ("*",), "cause": (">",),
}
LEMMA_RELATIONS = {"derivation": ("+",), "pertainsTo": ("\\",)}


def build_result(word_norm, file_pos, offset):
    syn = parse_synset(file_pos, offset)
    result = {"definition": syn["definition"], "partOfSpeech": syn["pos"]}
    word_lower = word_norm.replace("_", " ").lower()
    synonyms = [lm for lm in syn["lemmas"] if lm.lower() != word_lower]
    if synonyms:
        result["synonyms"] = synonyms
    antonyms, lemma_rel = [], {}
    for symbol, target, t_pos, src_w, tgt_w in syn["pointers"]:
        if symbol == "!" and src_w > 0:
            targets = synset_lemmas(t_pos if t_pos in POS_FILES else file_pos, target)
            if targets and tgt_w > 0 and tgt_w <= len(targets):
                antonyms.append(targets[tgt_w - 1])
        for key, symbols in LEMMA_RELATIONS.items():
            if symbol in symbols and src_w > 0:
                targets = synset_lemmas(t_pos if t_pos in POS_FILES else file_pos, target)
                if targets and tgt_w > 0 and tgt_w <= len(targets):
                    lemma_rel.setdefault(key, []).append(targets[tgt_w - 1])
    if antonyms:
        result["antonyms"] = list(dict.fromkeys(antonyms))
    for key, symbols in SYNSET_RELATIONS.items():
        values = []
        for symbol, target, t_pos, src_w, _tgt_w in syn["pointers"]:
            if symbol in symbols and src_w == 0:
                values.extend(synset_lemmas(t_pos if t_pos in POS_FILES else file_pos, target))
        if values:
            result[key] = list(dict.fromkeys(values))
    for key, values in lemma_rel.items():
        result[key] = list(dict.fromkeys(values))
    if syn["examples"]:
        result["examples"] = syn["examples"]
    return result


def word_senses(word_norm):
    """All (file_pos, offset) senses for a normalized lemma key."""
    return lemma_index.get(word_norm, [])


# Morphology: WordNet exception lists + a lite detachment rule set, so
# inflected queries ("running", "cats", "geese") resolve to base forms.
exceptions = {}
for _pos, _suffix in POS_FILES.items():
    path = os.path.join(DATA_DIR, f"{_suffix}.exc")
    if os.path.exists(path):
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                parts = line.split()
                if len(parts) == 2:
                    exceptions[parts[0].lower()] = parts[1].lower()
MORPH_RULES = [
    ("s", ""), ("ses", "ss"), ("xes", "x"), ("zes", "z"), ("ches", "ch"),
    ("shes", "sh"), ("men", "man"), ("ies", "y"), ("es", "e"), ("es", ""),
    ("ed", "e"), ("ed", ""), ("ing", "e"), ("ing", ""), ("er", ""), ("er", "e"),
    ("est", ""), ("est", "e"),
]


def resolve_word(raw):
    """Return (lemma_key, display) for a query word, or (None, None)."""
    norm = re.sub(r"\s+", "_", raw.strip().lower())
    if norm in lemma_index:
        return norm, norm.replace("_", " ")
    candidates = []
    if norm in exceptions:
        candidates.append(exceptions[norm])
    for suffix, replacement in MORPH_RULES:
        if norm.endswith(suffix) and len(norm) > len(suffix) + 1:
            candidates.append(norm[:-len(suffix)] + replacement)
    for cand in candidates:
        if cand in lemma_index:
            return cand, cand.replace("_", " ")
    return None, None


# ---------------------------------------------------------------- CMU dict
ARPA_TO_IPA = {
    "AA": "ɑ", "AE": "æ", "AH": "ʌ", "AO": "ɔ", "AW": "aʊ", "AY": "aɪ",
    "EH": "ɛ", "ER": "ɝ", "EY": "eɪ", "IH": "ɪ", "IY": "i", "OW": "oʊ",
    "OY": "ɔɪ", "UH": "ʊ", "UW": "u", "B": "b", "CH": "tʃ", "D": "d",
    "DH": "ð", "F": "f", "G": "ɡ", "HH": "h", "JH": "dʒ", "K": "k",
    "L": "l", "M": "m", "N": "n", "NG": "ŋ", "P": "p", "R": "r", "S": "s",
    "SH": "ʃ", "T": "t", "TH": "θ", "V": "v", "W": "w", "Y": "j",
    "Z": "z", "ZH": "ʒ",
}
VOWELS = {"AA", "AE", "AH", "AO", "AW", "AY", "EH", "ER", "EY", "IH",
          "IY", "OW", "OY", "UH", "UW"}

pronunciations = {}  # word -> [phoneme list, ...]
with open(os.path.join(DATA_DIR, "cmudict.dict"), encoding="utf-8", errors="replace") as fh:
    for line in fh:
        if line.startswith(";;;") or " " not in line:
            continue
        word, _, phones = line.partition("  ")
        if not phones.strip():
            word, _, phones = line.partition(" ")
        word = re.sub(r"\(\d+\)$", "", word.strip().lower())
        pronunciations.setdefault(word, []).append(phones.split())

rhyme_index = {}


def rhyme_key(phones):
    stripped = [re.sub(r"\d", "", p) for p in phones]
    vowel_positions = [i for i, p in enumerate(stripped) if p in VOWELS]
    if not vowel_positions:
        return None
    for stress in ("1", "2"):
        hits = [i for i in vowel_positions if phones[i].endswith(stress)]
        if hits:
            return tuple(stripped[hits[-1]:])
    return tuple(stripped[vowel_positions[-1]:])


for _word, _variants in pronunciations.items():
    _key = rhyme_key(_variants[0])
    if _key:
        rhyme_index.setdefault(_key, []).append(_word)


def ipa_string(phones):
    """IPA with stress marks: group phonemes into vowel-nucleus syllables,
    consonants between vowels join the following syllable's onset."""
    syllables, current = [], []
    for phone in phones:
        current.append(phone)
        if re.sub(r"\d", "", phone) in VOWELS:
            syllables.append(current)
            current = []
    if current:
        if syllables:
            syllables[-1].extend(current)
        else:
            syllables.append(current)
    out = []
    for syl in syllables:
        text = ""
        for phone in syl:
            base = re.sub(r"\d", "", phone)
            symbol = ARPA_TO_IPA.get(base, base.lower())
            if base == "AH":
                symbol = "ə" if phone.endswith("0") else "ʌ"
            if base == "ER":
                symbol = "ɚ" if phone.endswith("0") else "ɝ"
            text += symbol
        stress = next((p[-1] for p in syl if p[-1:].isdigit()), "")
        if stress == "1":
            text = "ˈ" + text
        elif stress == "2":
            text = "ˌ" + text
        out.append(text)
    return "".join(out)


def syllable_count_phones(phones):
    return sum(1 for p in phones if re.sub(r"\d", "", p) in VOWELS)


# Orthographic syllable splitter (documented approximation).
def split_syllables(word):
    w = word.lower()
    if len(w) <= 3:
        return [w]
    vowel_at = []
    for i, ch in enumerate(w):
        if ch in "aeiou":
            vowel_at.append(i)
        elif ch == "y" and i > 0 and w[i - 1] not in "aeiouy" and (i == len(w) - 1 or w[i + 1] not in "aeiou"):
            vowel_at.append(i)
    groups = []
    for i in vowel_at:
        if groups and i == groups[-1][-1] + 1:
            groups[-1].append(i)
        else:
            groups.append([i])
    # Silent trailing e (but consonant+le counts: "table" -> ta-ble).
    if (len(groups) > 1 and groups[-1] == [len(w) - 1] and w.endswith("e")
            and not (len(w) >= 3 and w[-2] == "l" and w[-3] not in "aeiouy")):
        groups.pop()
    if len(groups) <= 1:
        return [w]
    syllables, start = [], 0
    for gi in range(len(groups) - 1):
        end_of_group = groups[gi][-1] + 1
        next_start = groups[gi + 1][0]
        consonants = next_start - end_of_group
        cut = end_of_group if consonants <= 1 else end_of_group + 1
        syllables.append(w[start:cut])
        start = cut
    syllables.append(w[start:])
    return [s for s in syllables if s]


_syllable_cache = {}


def syllables_for(word):
    key = word.lower()
    if key in _syllable_cache:
        return _syllable_cache[key]
    parts = []
    for token in key.split():
        parts.extend(split_syllables(token))
    count = None
    if key in pronunciations:
        count = syllable_count_phones(pronunciations[key][0])
    if count is None:
        count = len(parts)
    while len(parts) > count and len(parts) > 1:
        parts[-2:] = [parts[-2] + parts[-1]]
    result = {"count": count, "list": parts}
    _syllable_cache[key] = result
    return result


# ---------------------------------------------------------------- Frequency
freq_counts = {}
_freq_total = 0
with open(os.path.join(DATA_DIR, "en_50k.txt"), encoding="utf-8", errors="replace") as fh:
    for line in fh:
        parts = line.split()
        if len(parts) == 2 and parts[1].isdigit():
            freq_counts[parts[0]] = int(parts[1])
            _freq_total += int(parts[1])


def frequency_for(word):
    count = freq_counts.get(word.lower())
    if count is None:
        return None
    return {"zipf": round(math.log10(count / _freq_total * 1e9), 2),
            "perMillion": round(count / _freq_total * 1e6, 2)}


# ---------------------------------------------------------------- Handlers
RELATION_KEYS = set(SYNSET_RELATIONS) | set(LEMMA_RELATIONS) | {
    "definitions", "synonyms", "antonyms", "examples",
    "pronunciation", "syllables", "frequency", "rhymes"}


def word_not_found(raw):
    return 404, {"error": "word_not_found",
                 "detail": f"'{raw}' is not in the WordNet lexicon this service covers "
                           f"(about 147,000 lemmas; slang and proper names are out of scope). "
                           f"Check the spelling or try the base form of the word."}


def full_record(word_norm, display):
    senses = word_senses(word_norm)
    if not senses:
        return None
    results = [build_result(word_norm, fp, off) for fp, off in senses]
    record = {"word": display, "results": results}
    record["syllables"] = syllables_for(display)
    if display.lower() in pronunciations:
        record["pronunciation"] = {"all": ipa_string(pronunciations[display.lower()][0])}
    freq = frequency_for(display)
    if freq:
        record["frequency"] = freq
    return record


def handle_word(params):
    raw = urllib.parse.unquote(params["word"])
    norm, display = resolve_word(raw)
    if norm is None:
        return word_not_found(raw)
    record = full_record(norm, display)
    if record is None:
        return word_not_found(raw)
    if norm != re.sub(r"\s+", "_", raw.strip().lower()):
        record["morphology"] = {"input": raw, "baseForm": display,
                                "note": "Inflected form resolved to its WordNet base form."}
    return 200, record


def handle_relation(params):
    raw = urllib.parse.unquote(params["word"])
    relation = params["relation"]
    if relation not in RELATION_KEYS:
        return 404, {"error": "not_found",
                     "detail": f"No relation '{relation}'. Supported: {', '.join(sorted(RELATION_KEYS))}."}
    norm, display = resolve_word(raw)
    if norm is None:
        return word_not_found(raw)
    if relation == "pronunciation":
        if display.lower() not in pronunciations:
            return 404, {"error": "pronunciation_not_found",
                         "detail": f"No CMU dictionary pronunciation for '{display}'."}
        return 200, {"word": display,
                     "pronunciation": {"all": ipa_string(pronunciations[display.lower()][0])}}
    if relation == "syllables":
        return 200, {"word": display, "syllables": syllables_for(display)}
    if relation == "frequency":
        freq = frequency_for(display)
        if freq is None:
            return 404, {"error": "frequency_not_found",
                         "detail": f"'{display}' is outside the 50,000-word frequency list."}
        return 200, {"word": display, "frequency": freq}
    if relation == "rhymes":
        variants = pronunciations.get(display.lower())
        if not variants:
            return 404, {"error": "rhymes_not_found",
                         "detail": f"No pronunciation for '{display}', so rhymes cannot be derived."}
        key = rhyme_key(variants[0])
        rhymes = [w for w in rhyme_index.get(key, []) if w != display.lower()]
        return 200, {"word": display, "rhymes": {"all": sorted(rhymes)[:100]}}
    results = [build_result(norm, fp, off) for fp, off in word_senses(norm)]
    if not results:
        return word_not_found(raw)
    if relation == "definitions":
        return 200, {"word": display,
                     "definitions": [{"definition": r["definition"],
                                      "partOfSpeech": r["partOfSpeech"]} for r in results]}
    values = []
    for r in results:
        values.extend(r.get(relation, []))
    return 200, {"word": display, relation: list(dict.fromkeys(values))}


def handle_search(params):
    letter_pattern = params.get("letterPattern")
    regex = None
    if letter_pattern:
        try:
            regex = re.compile(letter_pattern, re.IGNORECASE)
        except re.error as exc:
            return 400, {"error": "invalid_pattern", "detail": f"letterPattern is not a valid regex: {exc}"}
    def as_int(name):
        try:
            return int(params[name]) if params.get(name) else None
        except ValueError:
            return None
    letters_min, letters_max = as_int("lettersMin"), as_int("lettersMax")
    syl_min, syl_max = as_int("syllablesMin"), as_int("syllablesMax")
    freq_min, freq_max = (float(params["frequencyMin"]) if params.get("frequencyMin") else None,
                          float(params["frequencyMax"]) if params.get("frequencyMax") else None)
    pos_filter = params.get("partOfSpeech")
    has_details = [h for h in params.get("hasDetails", "").split(",") if h]
    limit = min(as_int("limit") or 100, 500)
    page = as_int("page") or 1
    matched = []
    for lemma, senses in lemma_index.items():
        display = lemma.replace("_", " ")
        if regex and not regex.search(display):
            continue
        letters = len(display.replace(" ", ""))
        if letters_min is not None and letters < letters_min:
            continue
        if letters_max is not None and letters > letters_max:
            continue
        if pos_filter:
            names = {POS_NAMES.get(fp, fp) for fp, _ in senses}
            if pos_filter.lower() not in names:
                continue
        if syl_min is not None or syl_max is not None:
            count = syllables_for(display)["count"]
            if syl_min is not None and count < syl_min:
                continue
            if syl_max is not None and count > syl_max:
                continue
        if freq_min is not None or freq_max is not None:
            freq = frequency_for(display)
            if freq is None:
                continue
            if freq_min is not None and freq["zipf"] < freq_min:
                continue
            if freq_max is not None and freq["zipf"] > freq_max:
                continue
        if has_details:
            ok = False
            for fp, off in senses:
                result = build_result(lemma, fp, off)
                if any(result.get(h) for h in has_details):
                    ok = True
                    break
            if not ok:
                continue
        matched.append(display)
    matched.sort()
    total = len(matched)
    start = (page - 1) * limit
    return 200, {"query": {k: v for k, v in params.items()},
                 "results": {"total": total, "data": matched[start:start + limit]}}


def handle_health(params):
    return 200, {"status": "ok", "service": "wordbase-dictionary",
                 "lemmas": len(lemma_index), "pronunciations": len(pronunciations),
                 "frequency_words": len(freq_counts),
                 "datasets": {"wordnet": "3.1 (Princeton, WordNet license)",
                              "pronunciation": "CMU Pronouncing Dictionary 0.7b",
                              "frequency": "FrequencyWords en_50k, OpenSubtitles 2018 (MIT)"}}


if __name__ == "__main__":
    run({
        "/words": handle_search,
        "/words/{word}": handle_word,
        "/words/{word}/{relation}": handle_relation,
        "/health": handle_health,
    }, int(os.environ.get("PORT", "8107")), "wordbase-dictionary")
