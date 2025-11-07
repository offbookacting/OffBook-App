# core/nlp_processor.py
from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple

try:
    import spacy  # optional boost
    _HAVE_SPACY = True
except Exception:
    _HAVE_SPACY = False

@dataclass
class DialogueBlock:
    speaker: str
    text: str
    raw_text: str
    start_line: int
    end_line: int
    parentheticals: List[str] = field(default_factory=list)

@dataclass
class ScriptParse:
    characters: Dict[str, int]
    blocks: List[DialogueBlock]
    character_aliases: Dict[str, List[str]]
    lines: List[str]

_SCENE_RE = re.compile(r'^(INT\.|EXT\.|INT/EXT\.|I/E\.|EST\.|INT\.? ?/ ?EXT\.?)\b')
_TRANSITION_RE = re.compile(r'(FADE IN:|FADE OUT\.?|CUT TO:|DISSOLVE TO:|SMASH CUT TO:|MATCH CUT TO:|WIPE TO:)\s*$')
_NAME_LINE_RE = re.compile(r"""^(?P<name>[A-Z0-9 .'\-]{2,}(?: [A-Z0-9 .'\-]{1,}){0,3})(?:\s*\((?:V\.O\.|O\.S\.|OS|OC|CONT'?D|CONT’D|PHONE|FILTERED)\))?\s*$""", re.X)
_NAME_BLACKLIST = {"INT","EXT","DAY","NIGHT","LATER","MOMENTS LATER","CONTINUOUS","CUT TO","FADE IN","FADE OUT","DISSOLVE TO","SMASH CUT TO","MATCH CUT TO","SUPER","TITLE","CREDITS"}
_PAREN_RE = re.compile(r'\(([^)]+)\)')
_MULTI_SPACE_RE = re.compile(r'\s{2,}')

def _is_mostly_caps(s: str) -> bool:
    letters = [ch for ch in s if ch.isalpha()]
    if not letters: return False
    caps = sum(1 for ch in letters if ch.isupper())
    return caps / len(letters) >= 0.9

def _is_scene_or_transition(line: str) -> bool:
    l = line.strip()
    return bool(_SCENE_RE.match(l)) or bool(_TRANSITION_RE.search(l))

def _clean_name(name: str) -> str:
    name = _MULTI_SPACE_RE.sub(' ', name.strip())
    name = re.sub(r'\s*\((?:V\.O\.|O\.S\.|OS|OC|CONT\'?D|CONT’D|PHONE|FILTERED)\)\s*$', '', name)
    name = name.strip(" .-").upper()
    if name in _NAME_BLACKLIST: return ""
    if len(name.split()) > 5: return ""
    return name

def _looks_like_name_line(line: str) -> Optional[str]:
    s = line.strip()
    if not s or _is_scene_or_transition(s): return None
    m = _NAME_LINE_RE.match(s)
    if not m: return None
    candidate = _clean_name(m.group('name'))
    if not candidate or not _is_mostly_caps(candidate): return None
    return candidate

def _strip_parentheticals(text: str):
    parenths = _PAREN_RE.findall(text)
    stripped = _PAREN_RE.sub('', text)
    stripped = _MULTI_SPACE_RE.sub(' ', stripped)
    stripped = '\n'.join(l.strip() for l in stripped.splitlines())
    return stripped.strip(), [p.strip() for p in parenths if p.strip()]

def _merge_soft_wraps(lines: List[str]) -> List[str]:
    merged: List[str] = []
    i = 0
    while i < len(lines):
        cur = lines[i].rstrip()
        if not cur:
            merged.append(cur); i += 1; continue
        if (not _looks_like_name_line(cur)) and (not _is_scene_or_transition(cur)):
            buff = cur; j = i + 1
            while j < len(lines):
                nxt = lines[j].strip()
                if not nxt: break
                if _looks_like_name_line(nxt) or _is_scene_or_transition(nxt): break
                buff = (buff[:-1] + nxt) if buff.endswith('-') else (buff + ' ' + nxt)
                j += 1
            merged.append(buff); i = j if j > i + 1 else i + 1
        else:
            merged.append(cur); i += 1
    return merged

def parse_script_text(full_text: str, use_spacy_person_boost: bool = True, spacy_model: str = "en_core_web_sm") -> ScriptParse:
    raw_lines = full_text.splitlines()
    lines = _merge_soft_wraps(raw_lines)

    nlp = None
    if use_spacy_person_boost and _HAVE_SPACY:
        try:
            nlp = spacy.load(spacy_model, disable=["tagger","lemmatizer","textcat"])
        except Exception:
            nlp = None

    name_at_idx: Dict[int, str] = {}
    for idx, line in enumerate(lines):
        cand = _looks_like_name_line(line)
        if cand: name_at_idx[idx] = cand

    blocks: List[DialogueBlock] = []
    i = 0
    while i < len(lines):
        if i in name_at_idx:
            speaker = name_at_idx[i]
            start = i + 1
            j = start
            collected: List[str] = []
            while j < len(lines):
                ln = lines[j]
                if not ln.strip() or j in name_at_idx or _is_scene_or_transition(ln): break
                collected.append(ln); j += 1
            raw_dialogue = "\n".join(collected).strip()
            cleaned, parenths = _strip_parentheticals(raw_dialogue)
            block = DialogueBlock(
                speaker=speaker,
                text=cleaned,
                raw_text=raw_dialogue,
                start_line=start if collected else i,
                end_line=(j - 1) if collected else i,
                parentheticals=parenths
            )
            if block.text: blocks.append(block)
            i = j
        else:
            i += 1

    freq: Dict[str, int] = {}
    for b in blocks: freq[b.speaker] = freq.get(b.speaker, 0) + 1
    aliases: Dict[str, List[str]] = {k: [k] for k in freq.keys()}

    if nlp is not None and blocks:
        seen_tokens: Dict[str, str] = {}
        for name in list(freq.keys()):
            for tok in name.split():
                if len(tok) > 1 and tok.isupper():
                    seen_tokens[tok] = name
        doc = nlp(full_text[:500000])
        for ent in doc.ents:
            if ent.label_ == "PERSON":
                up = ent.text.upper()
                for p in [p for p in re.split(r'\s+', up) if p.isalpha()]:
                    if p in seen_tokens:
                        canon = seen_tokens[p]
                        if up not in aliases[canon]:
                            aliases[canon].append(up)

    return ScriptParse(characters=freq, blocks=blocks, character_aliases=aliases, lines=lines)

def list_characters(parse: ScriptParse, sort_by_freq: bool = True) -> List[str]:
    chars = list(parse.characters.keys())
    chars.sort(key=lambda c: parse.characters[c], reverse=True) if sort_by_freq else chars.sort()
    return chars

def blocks_for_character(parse: ScriptParse, character: str) -> List[DialogueBlock]:
    canon = character.upper().strip()
    if canon in parse.characters:
        return [b for b in parse.blocks if b.speaker == canon]
    for k, alist in parse.character_aliases.items():
        if canon == k or canon in alist:
            return [b for b in parse.blocks if b.speaker == k]
    return [b for b in parse.blocks if canon in b.speaker]