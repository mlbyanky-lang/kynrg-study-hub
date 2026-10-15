"""
Daily Test 시험지 PDF 제작기 (교직원용)

- 같은 저장소의 단어장 CSV(day, word, meaning)를 그대로 사용
- 뜻 쓰기 시험: 선택한 DAY 범위에서 50문항을 뽑아 시험지(뜻 칸 비움)·정답지(뜻 채움) PDF
- 단어장과 이름이 같은 엑셀(MVP2.csv ↔ MVP2.xlsx: 데이·표제어·예문·동의어)이 있으면
  · 뜻 쓰기 시험에서 일부 표제어를 교재 동의어로 바꿔 출제 (정답은 원래 표제어의 뜻)
  · 동의어 4지선다: 교재 예문 + 교재 동의어(정답) + 다른 단어 동의어(오답)
- 실행: streamlit run exam_maker.py
"""

import difflib
import io
import os
import random
import re
import unicodedata

import pandas as pd
import streamlit as st
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

QUESTION_COUNT = 50
ROWS_PER_COLUMN = 25
REQUIRED_COLUMNS = {"day", "word", "meaning"}

# ==========================================
# 1. 한글 폰트
# ==========================================
FONT = "KR"
FONT_BOLD = "KR-Bold"

FONT_CANDIDATES = [
    # (보통, 굵게)
    ("fonts/NanumGothic.ttf", "fonts/NanumGothicBold.ttf"),  # 저장소 안 fonts 폴더
    ("/usr/share/fonts/truetype/nanum/NanumGothic.ttf",       # Streamlit Cloud (packages.txt: fonts-nanum)
     "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"),
    ("C:/Windows/Fonts/malgun.ttf", "C:/Windows/Fonts/malgunbd.ttf"),  # 내 PC(윈도우)에서 실행할 때
]

if os.environ.get("EXAM_FONT_DIR"):
    _d = os.environ["EXAM_FONT_DIR"]
    FONT_CANDIDATES.insert(0, (os.path.join(_d, "NanumGothic.ttf"), os.path.join(_d, "NanumGothicBold.ttf")))

_font_cmap = set()


def register_fonts():
    """사용 가능한 한글 폰트를 찾아 등록. 성공하면 True."""
    if FONT in pdfmetrics.getRegisteredFontNames():
        return True
    for regular, bold in FONT_CANDIDATES:
        if os.path.exists(regular) and os.path.exists(bold):
            pdfmetrics.registerFont(TTFont(FONT, regular))
            pdfmetrics.registerFont(TTFont(FONT_BOLD, bold))
            face = pdfmetrics.getFont(FONT).face
            _font_cmap.update(face.charToGlyph.keys())
            return True
    return False


# 폰트에 없는 기호를 비슷한 글자로 바꿔 네모(□)가 찍히지 않게
CHAR_REPLACE = {"․": "·", "‧": "·", "∙": "·", "\u00a0": " "}


def clean_text(text):
    text = unicodedata.normalize("NFC", str(text))
    text = "".join(CHAR_REPLACE.get(ch, ch) for ch in text)
    text = re.sub(r"\s+", " ", text).strip()
    if _font_cmap:
        # 폰트에 없는 결합 부호(악센트 등)는 제거
        text = "".join(
            ch for ch in text
            if ord(ch) in _font_cmap or not unicodedata.combining(ch)
        )
    return text


# ==========================================
# 2. 글자 맞춤 (칸 안에 들어가도록 줄바꿈·축소)
# ==========================================
def _wrap(text, font, size, width):
    """단어 단위로 줄바꿈, 한 단어가 칸보다 길면 글자 단위로 자른다."""
    lines, line = [], ""
    for token in text.split(" "):
        candidate = token if not line else f"{line} {token}"
        if pdfmetrics.stringWidth(candidate, font, size) <= width:
            line = candidate
            continue
        if line:
            lines.append(line)
            line = ""
        while pdfmetrics.stringWidth(token, font, size) > width:
            cut = len(token)
            while cut > 1 and pdfmetrics.stringWidth(token[:cut], font, size) > width:
                cut -= 1
            lines.append(token[:cut])
            token = token[cut:]
        line = token
    if line:
        lines.append(line)
    return lines


def fit_text(text, font, width, height, max_size, min_size, leading=1.18):
    """칸(width x height)에 들어가는 가장 큰 글자 크기와 줄 목록을 돌려준다."""
    # 1차: 단어 중간을 자르지 않고 들어가는 가장 큰 크기 / 2차: 그래도 안 되면 단어 중간 줄바꿈 허용
    for no_split in (True, False):
        size = max_size
        while size >= min_size:
            fits_words = all(pdfmetrics.stringWidth(t, font, size) <= width for t in text.split(" "))
            if fits_words or not no_split:
                lines = _wrap(text, font, size, width)
                if len(lines) * size * leading <= height:
                    return size, lines
            size = round(size - 0.25, 2)

    # 최소 크기로도 넘치면 들어가는 줄까지만 쓰고 말줄임
    size = min_size
    max_lines = max(1, int(height // (size * leading)))
    lines = _wrap(text, font, size, width)[:max_lines]
    last = lines[-1]
    while last and pdfmetrics.stringWidth(last + "…", font, size) > width:
        last = last[:-1]
    lines[-1] = last + "…"
    return size, lines


def draw_fitted(c, text, x, y_top, width, height, font, max_size, min_size, align="center"):
    """칸 왼쪽 위(x, y_top) 기준으로 글자를 세로 가운데 맞춰 그린다. (y는 PDF 좌표)"""
    if not text:
        return
    size, lines = fit_text(text, font, width, height, max_size, min_size)
    leading = size * 1.18
    block = leading * len(lines)
    # 첫 줄 기준선: 블록을 세로 가운데에 두고, 글자 높이의 약 78% 지점
    baseline = y_top - (height - block) / 2 - leading + (leading - size) / 2 + size * 0.22
    c.setFont(font, size)
    for line in lines:
        if align == "center":
            c.drawCentredString(x + width / 2, baseline, line)
        else:
            c.drawString(x, baseline, line)
        baseline -= leading


# ==========================================
# 3. 시험지 PDF (첨부 양식 좌표 그대로)
# ==========================================
PAGE_W, PAGE_H = A4

# 세로선 x 좌표 (왼쪽 판 / 오른쪽 판)
X_LEFT, X_MID, X_RIGHT = 15.25, 297.15, 579.15
COLS_LEFT = (X_LEFT, 32.95, 96.55, X_MID)    # No | 단어 | 뜻
COLS_RIGHT = (X_MID, 314.9, 378.5, X_RIGHT)

# 가로선 (위에서부터 잰 값 → PDF 좌표로 변환해서 사용)
HEADER_TOP, HEADER_BOTTOM = 14.65, 63.5
TABLE_TOP, TABLE_HEAD_BOTTOM, TABLE_BOTTOM = 67.95, 82.65, 751.65
ROW_H = (TABLE_BOTTOM - TABLE_HEAD_BOTTOM) / ROWS_PER_COLUMN
FOOT_LINES = (763.75, 781.6, 811.75)
FOOT_COLS = (15.3, 96.55, 297.2, 378.5, 579.2)

THICK, THIN = 1.7, 0.85
HEAD_GRAY = 0.851


def Y(top):
    """양식에서 잰 '위에서부터의 거리'를 PDF 좌표로."""
    return PAGE_H - top


def draw_page(c, items, opts, answer):
    # ---------- 머리말 ----------
    c.setLineWidth(THICK)
    c.rect(X_LEFT, Y(HEADER_BOTTOM), X_RIGHT - X_LEFT, HEADER_BOTTOM - HEADER_TOP)

    c.setFont(FONT, 9.8)
    for text, top in zip(opts["logo_lines"], (19.5, 34.4, 49.3)):
        c.drawCentredString(56.0, Y(top + 8.3), text)

    title_area = 330  # 가운데 제목이 쓸 수 있는 폭
    for text, top in zip(opts["title_lines"], (20.1, 43.4)):
        size = 16.0
        while size > 9 and pdfmetrics.stringWidth(text, FONT_BOLD, size) > title_area:
            size -= 0.5
        c.setFont(FONT_BOLD, size)
        c.drawCentredString(297.6, Y(top + 13.6), text)

    if answer:
        c.setFont(FONT, 10.7)
        c.drawRightString(569.0, Y(31.5), opts["range_label"])
        c.setFillColorRGB(0.75, 0.1, 0.1)
        c.setFont(FONT_BOLD, 11.5)
        c.drawRightString(569.0, Y(52.0), "정답지")
        c.setFillColorRGB(0, 0, 0)
    else:
        c.setFont(FONT, 10.7)
        c.drawRightString(569.0, Y(43.8), opts["range_label"])

    # ---------- 표 머리(회색) ----------
    c.setFillGray(HEAD_GRAY)
    c.rect(X_LEFT, Y(TABLE_HEAD_BOTTOM), X_RIGHT - X_LEFT, TABLE_HEAD_BOTTOM - TABLE_TOP, stroke=0, fill=1)
    c.setFillGray(0)

    c.setFont(FONT_BOLD, 6.2)
    for cols in (COLS_LEFT, COLS_RIGHT):
        for label, (a, b) in zip(("No", "단어", "뜻"), zip(cols, cols[1:])):
            c.drawCentredString((a + b) / 2, Y(78.3), label)

    # ---------- 표 선 ----------
    c.setLineWidth(THIN)
    for i in range(ROWS_PER_COLUMN):  # 가로선 (머리 아래선 포함)
        y = Y(TABLE_HEAD_BOTTOM + ROW_H * i)
        c.line(X_LEFT, y, X_RIGHT, y)
    for cols in (COLS_LEFT, COLS_RIGHT):  # 안쪽 세로선
        for x in cols[1:3]:
            c.line(x, Y(TABLE_TOP), x, Y(TABLE_BOTTOM))

    c.setLineWidth(THICK)  # 바깥 굵은 선 + 가운데 굵은 선
    c.rect(X_LEFT, Y(TABLE_BOTTOM), X_RIGHT - X_LEFT, TABLE_BOTTOM - TABLE_TOP)
    c.line(X_MID, Y(TABLE_TOP), X_MID, Y(TABLE_BOTTOM))

    # ---------- 문항 ----------
    pad = 2.5
    for idx in range(QUESTION_COUNT):
        cols = COLS_LEFT if idx < ROWS_PER_COLUMN else COLS_RIGHT
        row = idx % ROWS_PER_COLUMN
        top = Y(TABLE_HEAD_BOTTOM + ROW_H * row)
        x_no, x_word, x_mean, x_end = cols

        c.setFont(FONT, 8.9)
        c.drawCentredString((x_no + x_word) / 2, top - ROW_H / 2 - 3.1, str(idx + 1))

        if idx >= len(items):
            continue
        word, meaning, headword = (tuple(items[idx]) + (None,))[:3]
        if headword:  # 동의어로 낸 문항: 정답지에 원래 표제어를 함께 표시
            meaning = f"[{headword}] {meaning}"
        draw_fitted(c, word, x_word + pad, top - 1, x_mean - x_word - pad * 2, ROW_H - 2,
                    FONT, max_size=8.9, min_size=5.5, align="center")
        if answer:
            draw_fitted(c, meaning, x_mean + 3, top - 1, x_end - x_mean - 6, ROW_H - 2,
                        FONT, max_size=8.5, min_size=5.0, align="left")

    # ---------- 절취선 ----------
    c.setFont(FONT, 7.1)
    c.drawCentredString(297.6, Y(760.0), "=" * 37 + "     절     취     선     " + "=" * 37)

    # ---------- 회차 / 반명 / 이름 / 점수 ----------
    c.setLineWidth(THIN)
    for top in FOOT_LINES:
        c.line(FOOT_COLS[0], Y(top), FOOT_COLS[-1], Y(top))
    for x in FOOT_COLS:
        c.line(x, Y(FOOT_LINES[0]), x, Y(FOOT_LINES[-1]))

    c.setFont(FONT, 9.8)
    for label, (a, b) in zip(("회차", "반명", "이름", "점수"), zip(FOOT_COLS, FOOT_COLS[1:])):
        c.drawCentredString((a + b) / 2, Y(776.0), label)

    c.setFont(FONT, 19.6)
    c.drawRightString(575.8, Y(805.0), f"/ {QUESTION_COUNT}")


def build_pdf(items, opts, answer=False):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    c.setTitle(f"{opts['title_lines'][1]} {opts['range_label']} {'정답지' if answer else '시험지'}")
    draw_page(c, items, opts, answer)
    c.showPage()
    c.save()
    return buffer.getvalue()


# ==========================================
# 4. 단어장 데이터
# ==========================================
def day_number(value):
    m = re.search(r"\d+", str(value))
    return int(m.group()) if m else None


def get_voca_files():
    files = []
    for f in sorted(os.listdir(".")):
        if not f.lower().endswith(".csv"):
            continue
        try:
            cols = set(pd.read_csv(f, encoding="utf-8-sig", nrows=0).columns)
        except Exception:
            continue
        if REQUIRED_COLUMNS <= cols:
            files.append(f)
    return files


@st.cache_data
def load_voca(path):
    df = pd.read_csv(path, encoding="utf-8-sig")
    df = df.dropna(subset=["day", "word", "meaning"]).copy()
    df["day_no"] = df["day"].map(day_number)
    df = df.dropna(subset=["day_no"])
    df["day_no"] = df["day_no"].astype(int)
    df["word"] = df["word"].astype(str).str.strip()
    df["meaning"] = df["meaning"].astype(str).str.strip()
    return df


def default_book_label(filename):
    stem = os.path.splitext(filename)[0]
    m = re.fullmatch(r"(?i)mvp\s*(\d+)", stem)
    return f"MVP Vol.{m.group(1)}" if m else stem


def pick_items(df, start, end, seed, count=50):
    pool = df[(df["day_no"] >= start) & (df["day_no"] <= end)]
    pool = pool.drop_duplicates(subset="word")
    rows = list(pool[["word", "meaning"]].itertuples(index=False, name=None))
    rng = random.Random(seed)
    if len(rows) > count:
        rows = rng.sample(rows, count)
    else:
        rng.shuffle(rows)
    return [(clean_text(w), clean_text(m)) for w, m in rows], len(pool)


# ==========================================
# 5. 동의어·예문 데이터 (MVP1.xlsx, MVP2.xlsx)
# ==========================================
# 단어장 CSV와 이름이 같은 엑셀(MVP2.csv ↔ MVP2.xlsx)을 함께 읽는다.
# 엑셀 형식: 데이 | 표제어 | 예문 | 동의어 1 | 동의어 2 | ... (동의어 칸은 몇 개든 됨)
SYN_TITLE_DEFAULT = "Daily Test (동의어)"
SYN_QUESTION = "다음 단어와 의미가 가장 유사한 것을 고르시오: "

POS_RE = re.compile(r"^\s*(vt|vi|v|n|a|ad|adv|prep|conj)\s*\.", re.I)
POS_GROUP = {"vt": "v", "vi": "v", "v": "v", "n": "n", "a": "a", "ad": "ad", "adv": "ad",
             "prep": "prep", "conj": "conj"}


def part_of_speech(meaning):
    m = POS_RE.match(str(meaning))
    return POS_GROUP.get(m.group(1).lower()) if m else None


def synonym_file_for(voca_file):
    stem = os.path.splitext(voca_file)[0]
    for ext in (".xlsx", ".XLSX"):
        if os.path.exists(stem + ext):
            return stem + ext
    return None


def _clean_synonym(value):
    s = clean_text(value).replace("|", "l")          # 스캔 오류: |iberal → liberal
    s = re.sub(r"^[\s,;.·]+|[\s,;.·]+$", "", s)       # 앞뒤 쉼표·마침표 제거
    return s


def _clean_example(value):
    return clean_text(value).replace("|", "l").strip().strip('"“”')


@st.cache_data
def load_synonyms(xlsx_path, voca_file):
    """엑셀을 읽어 단어장 표제어(day, word)에 붙인다.
    반환: 뜻(의미)별 행 목록 DataFrame [day_no, word, example, synonyms(list)]"""
    raw = pd.read_excel(xlsx_path, sheet_name=0, header=0, dtype=str)
    raw = raw.dropna(how="all")
    cols = list(raw.columns)
    day_col, word_col, ex_col = cols[0], cols[1], cols[2]
    syn_cols = cols[3:]

    rows = []
    for _, r in raw.iterrows():
        day = day_number(r[day_col])
        word = clean_text(r[word_col]) if pd.notna(r[word_col]) else ""
        if day is None or not word:
            continue
        syns = []
        for c in syn_cols:
            if pd.notna(r[c]):
                s = _clean_synonym(r[c])
                if s and s.lower() != word.lower() and s.lower() not in (x.lower() for x in syns):
                    syns.append(s)
        example = _clean_example(r[ex_col]) if pd.notna(r[ex_col]) else ""
        rows.append({"day_no": day, "xl_word": word, "example": example, "synonyms": syns})
    syn = pd.DataFrame(rows)

    # 엑셀 표제어 오타(adequete 등)는 같은 DAY 안에서 가장 비슷한 단어장 표제어로 맞춘다
    voca = load_voca(voca_file)
    by_day = {}
    for d, w in zip(voca["day_no"], voca["word"]):
        by_day.setdefault(d, {})[w.lower()] = w

    def match(row):
        words = by_day.get(row["day_no"], {})
        key = row["xl_word"].lower()
        if key in words:
            return words[key]
        close = difflib.get_close_matches(key, list(words), n=1, cutoff=0.8)
        return words[close[0]] if close else None

    syn["word"] = syn.apply(match, axis=1)
    return syn.dropna(subset=["word"]).reset_index(drop=True)


def _similar_form(a, b):
    """glorify / glorified, domestic / domesticated 처럼 같은 뿌리면 True."""
    a, b = a.lower(), b.lower()
    n = min(len(a), len(b), 5)
    return n >= 4 and a[:n] == b[:n]


def trusted_words(syn_df, voca_df):
    """교재에 두 번 이상 나오거나 표제어인 단어 — 한 번만 나오는 단어는 스캔 오타일 가능성이 커서 뒤로 미룬다."""
    cnt = {}
    for lst in syn_df["synonyms"]:
        for x in lst:
            cnt[x.lower()] = cnt.get(x.lower(), 0) + 1
    return {k for k, v in cnt.items() if v >= 2} | {w.lower() for w in voca_df["word"]}


def _choose_synonym(word, synonyms, rng, avoid=(), trusted=None):
    """한 단어짜리·형태가 다른·교재에 자주 나오는 동의어를 우선해서 하나 고른다."""
    avoid = {a.lower() for a in avoid}
    cands = [s for s in synonyms if s.lower() not in avoid]
    trusted = trusted or set()
    for rule in (lambda s: " " not in s and not _similar_form(s, word) and s.lower() in trusted,
                 lambda s: " " not in s and not _similar_form(s, word),
                 lambda s: not _similar_form(s, word),
                 lambda s: True):
        good = [s for s in cands if rule(s)]
        if good:
            return rng.choice(good)
    return None


def example_has_word(word, example):
    """예문에 표제어(또는 변형)가 들어 있는지 — 아니면 표에서 '확인' 표시."""
    stem = word.lower().split()[0][: max(3, min(len(word), 5) - 1)]
    return stem in example.lower()


# ---------- 뜻 쓰기 시험: 일부 표제어를 동의어로 바꿔 출제 ----------
def apply_synonym_mix(items, syn_df, ratio, seed, trusted=None):
    """items: [(word, meaning)] → [(출제 단어, 뜻, 원래 표제어 or None)]"""
    rng = random.Random(seed + 1)
    syn_map = {}
    for w, lst in zip(syn_df["word"], syn_df["synonyms"]):
        syn_map.setdefault(w, []).extend(x for x in lst if x not in syn_map.get(w, []))

    eligible = [i for i, (w, _) in enumerate(items) if syn_map.get(w)]
    target = min(len(eligible), round(len(items) * ratio))
    chosen = set(rng.sample(eligible, target))

    used = {w.lower() for w, _ in items}
    result = []
    for i, (word, meaning) in enumerate(items):
        if i in chosen:
            s = _choose_synonym(word, syn_map[word], rng, avoid=used, trusted=trusted)
            if s:
                used.add(s.lower())
                result.append((s, meaning, word))
                continue
        result.append((word, meaning, None))
    return result, len(eligible)


# ---------- 4지선다 동의어 시험 ----------
def build_synonym_table(voca_df, syn_df, start, end, count, seed):
    rng = random.Random(seed)
    pos_of = dict(zip(voca_df["word"], voca_df["meaning"].map(part_of_speech)))
    trusted = trusted_words(syn_df, voca_df)

    # 표제어별 전체 동의어 (오답에서 빼기 위해)
    all_syn = {}
    for w, lst in zip(syn_df["word"], syn_df["synonyms"]):
        all_syn.setdefault(w, set()).update(x.lower() for x in lst)

    # 같은 동의어 묶음에 함께 나온 단어끼리 연결 (expert·specialist처럼 뜻이 가까운 오답을 막기 위해)
    related = {}
    for w, syns in all_syn.items():
        group = syns | {w.lower()}
        for x in group:
            related.setdefault(x, set()).update(group)

    # 오답 후보: 책 전체의 다른 표제어 동의어 (품사는 원래 표제어 기준)
    pool = []
    for w, syns in all_syn.items():
        for s in syns:
            pool.append((s, w, pos_of.get(w)))

    in_range = syn_df[(syn_df["day_no"] >= start) & (syn_df["day_no"] <= end)]
    in_range = in_range[in_range["synonyms"].map(len) > 0]
    words = list(dict.fromkeys(in_range["word"]))          # 순서 유지 중복 제거
    picked = rng.sample(words, min(count, len(words)))

    rows = []
    for word in picked:
        senses = in_range[in_range["word"] == word]
        sense = senses.iloc[rng.randrange(len(senses))]    # 뜻이 여러 개면 그중 하나
        answer = _choose_synonym(word, sense["synonyms"], rng, trusted=trusted) or ""

        mine = all_syn.get(word, set()) | {word.lower()}
        near = set().union(*(related.get(x, set()) for x in mine | {answer.lower()}))
        pos = pos_of.get(word)

        def ok(cand, src):
            # 이 표제어의 동의어와 겹치는 표제어에서 나온 후보는 뜻이 가까울 수 있어 제외
            return (cand.lower() not in mine and cand.lower() not in near and src != word
                    and not (all_syn.get(src, set()) & mine)
                    and not _similar_form(cand, answer) and not _similar_form(cand, word))

        cands = [(c, s, p) for c, s, p in pool if c in trusted and ok(c, s)]
        for narrow in (lambda c, p: p == pos and " " not in c, lambda c, p: " " not in c, lambda c, p: True):
            sub = [c for c, _, p in cands if narrow(c, p)]
            if len(set(sub)) >= 3:
                cands_final = list(dict.fromkeys(sub))
                break
        else:
            cands_final = list(dict.fromkeys(c for c, _, _ in cands))
        wrong = rng.sample(cands_final, min(3, len(cands_final)))
        wrong += [""] * (3 - len(wrong))

        example = sense["example"]
        rows.append({
            "확인": "" if example_has_word(word, example) else "⚠ 예문 확인",
            "단어": word,
            "정답(동의어)": answer,
            "오답1": wrong[0], "오답2": wrong[1], "오답3": wrong[2],
            "예문": example,
            "교재 동의어(참고)": ", ".join(sense["synonyms"]),
        })
    return pd.DataFrame(rows, index=range(1, len(rows) + 1)), len(words)


def table_to_questions(table, seed):
    """편집이 끝난 표 → 문항 목록. 정답 위치는 A~D에 고르게."""
    rng = random.Random(seed)
    positions = [i % 4 for i in range(len(table))]
    rng.shuffle(positions)
    questions = []
    for pos, (_, r) in zip(positions, table.iterrows()):
        wrong = [clean_text(r[c]) for c in ("오답1", "오답2", "오답3")]
        rng.shuffle(wrong)
        choices = wrong[:pos] + [clean_text(r["정답(동의어)"])] + wrong[pos:]
        questions.append({
            "word": clean_text(r["단어"]),
            "example": clean_text(r["예문"]),
            "choices": choices,
            "answer": pos,
        })
    return questions


# ==========================================
# 6. 동의어 시험지 PDF (첨부 양식 기준, 선택지는 한 줄)
# ==========================================
SYN_MARGIN_L = 42.5
SYN_MARGIN_R = PAGE_W - 42.5
SYN_FIRST_Q_TOP = 149.5
SYN_BOTTOM = PAGE_H - 45
LETTERS = "ABCD"


def _syn_header(c, range_label, title):
    c.setFillGray(0)
    c.setFont(FONT_BOLD, 14)
    c.drawCentredString(PAGE_W / 2, Y(56.5), range_label)
    c.setLineWidth(1)
    c.rect(184.3, Y(119.1), 411.0 - 184.3, 119.1 - 85.0)
    size = 16
    while size > 10 and pdfmetrics.stringWidth(title, FONT_BOLD, size) > 215:
        size -= 0.5
    c.setFont(FONT_BOLD, size)
    c.drawCentredString(PAGE_W / 2, Y(107.5), title)


def _fit_one_line(text, font, size, width, min_size=7):
    while size > min_size and pdfmetrics.stringWidth(text, font, size) > width:
        size -= 0.25
    return size


def _question_block(c, n, q, top, measure_only=False):
    """문항 하나를 그리고 차지한 높이를 돌려준다."""
    width = SYN_MARGIN_R - SYN_MARGIN_L
    y = top

    # 1) 발문 + 단어
    stem = f"{n}. {SYN_QUESTION}{q['word']}"
    size = _fit_one_line(stem, FONT_BOLD, 10.5, width)
    if not measure_only:
        c.setFillGray(0)
        c.setFont(FONT_BOLD, size)
        c.drawString(SYN_MARGIN_L, Y(y + 8.6), stem)
    y += 18.7

    # 2) 예문 (회색, 길면 줄바꿈)
    if q["example"]:
        lines = _wrap(f"\"{q['example']}\"", FONT_BOLD, 10, width - 8)
        for line in lines:
            if not measure_only:
                c.setFillGray(0.502)
                c.setFont(FONT_BOLD, 10)
                c.drawString(SYN_MARGIN_L + 8, Y(y + 8.2), line)
            y += 13.5
        y += 1.6

    # 3) 선택지 한 줄 (A~D를 4등분 위치에)
    col_w = width / 4
    if not measure_only:
        c.setFillGray(0)
        for i, choice in enumerate(q["choices"]):
            text = f"({LETTERS[i]}) {choice}"
            s = _fit_one_line(text, FONT_BOLD, 10.5, col_w - 6)
            c.setFont(FONT_BOLD, s)
            c.drawString(SYN_MARGIN_L + col_w * i, Y(y + 8.6), text)
    y += 10.5

    return y - top


SYN_GAP = 20  # 문항 사이 여백


def build_synonym_exam_pdf(questions, range_label, title):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    c.setTitle(f"{title} {range_label}")

    _syn_header(c, range_label, title)
    top = SYN_FIRST_Q_TOP
    for n, q in enumerate(questions, start=1):
        h = _question_block(c, n, q, top, measure_only=True)
        if top + h > SYN_BOTTOM:
            c.showPage()
            _syn_header(c, range_label, title)
            top = SYN_FIRST_Q_TOP
        _question_block(c, n, q, top)
        top += h + SYN_GAP

    c.showPage()
    c.save()
    return buffer.getvalue()


def build_synonym_answer_pdf(questions, range_label, title):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    c.setTitle(f"{title} {range_label} Answer Key")

    c.setFont(FONT_BOLD, 16)
    c.drawString(SYN_MARGIN_L, Y(57.5), "Answer Key")
    c.setFont(FONT, 10)
    c.drawRightString(SYN_MARGIN_R, Y(57.5), f"{title}  |  {range_label}")

    per_col = 40
    col_w = (SYN_MARGIN_R - SYN_MARGIN_L) / 2
    for i, q in enumerate(questions):
        col, row = divmod(i, per_col)
        x = SYN_MARGIN_L + col_w * col
        y = 77.0 + row * 17.0
        letter = LETTERS[q["answer"]]
        text = f"{i + 1}. ({letter})   {q['word']} = {q['choices'][q['answer']]}"
        c.setFont(FONT_BOLD, _fit_one_line(text, FONT_BOLD, 10, col_w - 10))
        c.drawString(x, Y(y + 8.0), text)

    c.showPage()
    c.save()
    return buffer.getvalue()


# ==========================================
# 7. 화면
# ==========================================
def check_admin():
    if st.session_state.get("admin_ok"):
        return True

    st.title("🔒 시험지 제작기")
    st.info("교직원 전용 화면입니다.")
    pwd = st.text_input("관리자 비밀번호를 입력하세요:", type="password")
    if st.button("입장하기"):
        try:
            correct = st.secrets["ADMIN_PASSWORD"]
        except Exception:
            st.error("ADMIN_PASSWORD가 Secrets에 설정되어 있지 않습니다.")
            return False
        if pwd == correct:
            st.session_state.admin_ok = True
            st.rerun()
        else:
            st.error("❌ 비밀번호가 올바르지 않습니다.")
    return False


def headword_page(df, voca_file, start, end, range_label):
    xlsx = synonym_file_for(voca_file)
    book = default_book_label(voca_file)

    st.subheader("2. 출제 방식")
    if xlsx:
        ratio = st.slider("동의어로 바꿔 낼 비율", 0, 100, 50, step=10, format="%d%%",
                          help="뽑힌 50개 중 이 비율만큼 표제어 대신 교재 동의어를 냅니다. 정답은 원래 표제어의 뜻입니다.")
    else:
        ratio = 0
        st.caption(f"'{os.path.splitext(voca_file)[0]}.xlsx'(동의어 파일)가 없어 표제어로만 출제합니다.")

    st.subheader("3. 시험지 문구")
    col1, col2 = st.columns(2)
    title1 = col1.text_input("제목 1행", "2027년 대비 Daily Test")
    title2 = col2.text_input("제목 2행", f"{book} ({'동의어+표제어' if ratio else '표제어'})")
    campus = st.text_input("캠퍼스명 (왼쪽 위)", "일산캠퍼스")

    opts = {
        "logo_lines": ("대학편입 No.1", "김영편입", campus),
        "title_lines": (title1, title2),
        "range_label": range_label,
    }

    st.subheader("4. 문항")
    if st.button("🔀 문항 다시 뽑기"):
        st.session_state.exam_seed = random.randrange(1_000_000)

    seed = st.session_state.exam_seed
    items, pool_size = pick_items(df, start, end, seed, QUESTION_COUNT)
    if ratio:
        syn_df = load_synonyms(xlsx, voca_file)
        items, eligible = apply_synonym_mix(items, syn_df, ratio / 100, seed, trusted_words(syn_df, df))
        n_syn = sum(1 for _, _, h in items if h)
        st.write(f"범위 안 단어 **{pool_size}개** 중 **{len(items)}개**를 뽑았고, 그중 **{n_syn}개**를 동의어로 냈습니다.")
        if n_syn < round(len(items) * ratio / 100):
            st.caption(f"뽑힌 단어 중 교재 동의어가 있는 단어가 {eligible}개라서 동의어 문항이 목표보다 적습니다.")
    else:
        items = [(w, m, None) for w, m in items]
        st.write(f"범위 안 단어 **{pool_size}개** 중 **{len(items)}개**를 무작위로 뽑았습니다.")

    if pool_size < QUESTION_COUNT:
        st.warning(f"선택한 범위의 단어가 {pool_size}개라서 {pool_size}문항만 들어갑니다. 나머지 칸은 비워집니다.")

    with st.expander("뽑힌 문항 미리보기"):
        st.dataframe(
            pd.DataFrame([(w, h or "", m) for w, m, h in items], columns=["출제 단어", "원래 표제어", "정답(뜻)"],
                         index=range(1, len(items) + 1)),
            width="stretch",
        )

    st.subheader("5. PDF 내려받기")
    base = f"DailyTest_{book}_{range_label}".replace(" ", "")
    d1, d2 = st.columns(2)
    d1.download_button("📄 시험지 PDF", build_pdf(items, opts, answer=False), f"{base}_시험지.pdf",
                       "application/pdf", width="stretch", type="primary")
    d2.download_button("✅ 정답지 PDF", build_pdf(items, opts, answer=True), f"{base}_정답지.pdf",
                       "application/pdf", width="stretch")
    if ratio:
        st.caption("정답지에서 동의어 문항은 뜻 앞에 [원래 표제어]를 붙여 채점할 때 알아볼 수 있게 했습니다.")


def synonym_page(df, voca_file, start, end):
    xlsx = synonym_file_for(voca_file)
    if not xlsx:
        st.warning(f"동의어 4지선다는 동의어·예문 파일이 있어야 합니다. "
                   f"'{os.path.splitext(voca_file)[0]}.xlsx'를 저장소에 올려 주세요.")
        st.stop()
    syn_df = load_synonyms(xlsx, voca_file)

    st.subheader("2. 시험지 문구")
    col1, col2 = st.columns([2, 1])
    title = col1.text_input("제목", SYN_TITLE_DEFAULT)
    count = col2.number_input("문항 수", min_value=5, max_value=50, value=20, step=5)
    range_label = f"범위: Day {start} ~ Day {end}" if start != end else f"범위: Day {start}"

    st.subheader("3. 문항")
    st.caption("표제어·예문·정답 동의어는 교재 파일에서, 오답 3개는 같은 교재의 다른 단어 동의어 중 품사가 같은 것에서 뽑습니다.")
    if st.button("🔀 문항 다시 뽑기"):
        st.session_state.exam_seed = random.randrange(1_000_000)

    seed = st.session_state.exam_seed
    table, available = build_synonym_table(df, syn_df, start, end, int(count), seed)
    if available < count:
        st.warning(f"선택한 범위에서 동의어가 있는 표제어가 {available}개라서 {available}문항만 만들었습니다.")

    flagged = (table["확인"] != "").sum()
    st.caption("표에서 바로 고칠 수 있고, 고친 내용이 그대로 PDF에 들어갑니다."
               + (f" ⚠ 표시 {flagged}개는 예문에 표제어가 안 보여 확인이 필요한 문항입니다." if flagged else ""))
    edited = st.data_editor(
        table,
        width="stretch",
        num_rows="fixed",
        disabled=["확인", "단어", "교재 동의어(참고)"],
        column_config={
            "확인": st.column_config.TextColumn(width="small"),
            "예문": st.column_config.TextColumn(width="large"),
        },
        key=f"syn_editor_{voca_file}_{start}_{end}_{count}_{seed}",
    )

    blank = edited[edited[["정답(동의어)", "오답1", "오답2", "오답3"]].apply(
        lambda r: any(not str(v).strip() for v in r), axis=1)]
    if len(blank):
        st.error(f"정답·오답 칸이 비어 있는 문항이 있습니다: {', '.join(map(str, blank.index))}번")
        return

    st.subheader("4. PDF 내려받기")
    questions = table_to_questions(edited, seed)
    base = f"DailyTest_동의어_{default_book_label(voca_file)}_Day{start}-{end}".replace(" ", "")
    d1, d2 = st.columns(2)
    d1.download_button("📄 시험지 PDF", build_synonym_exam_pdf(questions, range_label, title),
                       f"{base}_시험지.pdf", "application/pdf", width="stretch", type="primary")
    d2.download_button("✅ 정답지 PDF", build_synonym_answer_pdf(questions, range_label, title),
                       f"{base}_정답지.pdf", "application/pdf", width="stretch")


def main():
    st.set_page_config(page_title="김영편입 일산 - 시험지 제작기", page_icon="📝", layout="wide")

    if not check_admin():
        st.stop()

    st.title("📝 Daily Test 시험지 제작기")

    if not register_fonts():
        st.error(
            "한글 폰트를 찾지 못했습니다. 저장소에 packages.txt(내용: fonts-nanum)가 있는지 "
            "확인하고 앱을 재시작해 주세요."
        )
        st.stop()

    files = get_voca_files()
    if not files:
        st.error("단어장 CSV(day, word, meaning)가 저장소에 없습니다.")
        st.stop()

    exam_type = st.radio("시험 유형", ["뜻 쓰기 (50문항)", "동의어 4지선다"], horizontal=True)

    st.subheader("1. 출제 범위")
    voca_file = st.selectbox("단어장", files)
    df = load_voca(voca_file)
    days = sorted(df["day_no"].unique())

    start, end = st.select_slider(
        "DAY 범위",
        options=days,
        value=(days[0], days[min(3, len(days) - 1)]),
        format_func=lambda d: f"Day {d:02d}",
    )

    key = (voca_file, start, end)
    if st.session_state.get("exam_key") != key:
        st.session_state.exam_key = key
        st.session_state.exam_seed = random.randrange(1_000_000)

    if exam_type.startswith("뜻 쓰기"):
        range_label = f"Day {start:02d}" if start == end else f"Day {start:02d} - Day {end:02d}"
        headword_page(df, voca_file, start, end, range_label)
    else:
        synonym_page(df, voca_file, start, end)


if __name__ == "__main__":
    main()
