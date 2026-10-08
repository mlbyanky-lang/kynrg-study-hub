import streamlit as st
from openai import OpenAI
import pandas as pd
import random
import os

st.set_page_config(
    page_title="김영편입 노량진 - 종합 학습 플랫폼",
    page_icon="🚀",
    layout="wide"
)

# 퀴즈 보기 버튼의 긴 뜻이 말줄임(...)으로 잘리지 않고 줄바꿈되도록
st.markdown(
    """
    <style>
    div.stButton > button,
    div[data-testid="stButton"] button {
        height: auto;
        min-height: 2.5rem;
        white-space: normal;
    }
    div.stButton > button p,
    div.stButton > button div,
    div[data-testid="stButton"] button p,
    div[data-testid="stButton"] button div {
        white-space: normal !important;
        overflow: visible !important;
        text-overflow: clip !important;
        overflow-wrap: anywhere;
        word-break: keep-all;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

REQUIRED_COLUMNS = {"day", "word", "meaning"}
MAX_ANALYSIS_LENGTH = 1500

# ==========================================
# 1. 수강생 인증
# ==========================================
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🔒 김영편입 노량진 학습 플랫폼")
    st.info("본 서비스는 수강생 전용 프리미엄 학습 시스템입니다.")

    pwd = st.text_input("수강생 인증 코드를 입력하세요:", type="password")

    if st.button("입장하기"):
        try:
            if pwd == st.secrets["APP_PASSWORD"]:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("❌ 인증 코드가 올바르지 않습니다. 학원 데스크에 문의하세요.")
        except KeyError:
            st.error("APP_PASSWORD가 설정되어 있지 않습니다. 관리자에게 문의하세요.")

    st.stop()

# ==========================================
# 2. AI 설정 (회사 LLM 게이트웨이 - OpenAI 모델)
# ==========================================
MODEL_NAME = "gpt-5.6-terra"

REQUIRED_SECRETS = ["OPENAI_API_KEY", "OPENAI_BASE_URL"]

client = None
client_error = None

try:
    # 값은 표시하지 않고 이름만 확인
    missing_secrets = [name for name in REQUIRED_SECRETS if name not in st.secrets]

    if missing_secrets:
        client_error = (
            f"Secrets에 없는 이름: {', '.join(missing_secrets)} / "
            f"앱이 현재 읽은 이름: {', '.join(st.secrets.keys()) or '없음'}"
        )
    else:
        client = OpenAI(
            api_key=st.secrets["OPENAI_API_KEY"],
            base_url=st.secrets["OPENAI_BASE_URL"],
        )
except Exception as e:
    client_error = type(e).__name__
    print(f"[AI 설정 오류] {type(e).__name__}: {e}", flush=True)

# ==========================================
# 3. 단어장 데이터 처리 함수 (공용)
# ==========================================
def get_all_voca_files():
    return sorted([f for f in os.listdir(".") if f.lower().endswith(".csv")])

@st.cache_data
def load_selected_voca(file_path):
    try:
        df = pd.read_csv(file_path, encoding="utf-8-sig")

        missing_columns = REQUIRED_COLUMNS - set(df.columns)
        if missing_columns:
            st.error(f"CSV 파일에 필요한 컬럼이 없습니다: {', '.join(missing_columns)}")
            return None

        df = df.dropna(subset=["day", "word", "meaning"])
        df["day"] = df["day"].astype(str)
        df["word"] = df["word"].astype(str)
        df["meaning"] = df["meaning"].astype(str)

        return df

    except Exception as e:
        st.error(f"CSV 파일을 불러오는 중 오류가 발생했습니다: {e}")
        return None

def reset_quiz_stats():
    st.session_state.total_count = 0
    st.session_state.correct_count = 0
    st.session_state.wrong_words = []

def initialize_quiz(filtered_df, full_df):
    target_row = filtered_df.sample(n=1).iloc[0]

    answer = target_row["meaning"]
    candidates = full_df[full_df["meaning"] != answer]["meaning"].drop_duplicates().tolist()

    if len(candidates) >= 3:
        distractors = random.sample(candidates, 3)
    else:
        distractors = candidates

    options = distractors + [answer]
    random.shuffle(options)

    st.session_state.quiz_data = {
        "word": target_row["word"],
        "answer": answer,
        "options": options,
        "solved": False,
        "selected": None,
    }

# ==========================================
# 3-1. 수학 공식 데이터 처리 함수
# ==========================================
MATH_FORMULAS_FILE = "math_formulas.csv"
MATH_REQUIRED_COLUMNS = {"subject", "category", "name", "formula"}
MATH_SUBJECT_ORDER = ["미분", "적분", "선형대수", "다변수미적분", "공학수학"]

@st.cache_data
def load_math_formulas():
    try:
        df = pd.read_csv(MATH_FORMULAS_FILE, encoding="utf-8-sig")

        missing_columns = MATH_REQUIRED_COLUMNS - set(df.columns)
        if missing_columns:
            st.error(f"CSV 파일에 필요한 컬럼이 없습니다: {', '.join(missing_columns)}")
            return None

        df = df.dropna(subset=["subject", "category", "name", "formula"])
        df["subject"] = df["subject"].astype(str)
        df["category"] = df["category"].astype(str)
        df["name"] = df["name"].astype(str)
        df["formula"] = df["formula"].astype(str)

        return df

    except FileNotFoundError:
        return None
    except Exception as e:
        st.error(f"수학 공식 파일을 불러오는 중 오류가 발생했습니다: {e}")
        return None

def get_subjects_in_order(df):
    present = set(df["subject"].unique())
    ordered = [s for s in MATH_SUBJECT_ORDER if s in present]
    ordered += [s for s in present if s not in MATH_SUBJECT_ORDER]
    return ordered

def reset_math_quiz_stats():
    st.session_state.math_total_count = 0
    st.session_state.math_correct_count = 0
    st.session_state.math_wrong_items = []

def initialize_math_quiz(filtered_df, full_df):
    target_row = filtered_df.sample(n=1).iloc[0]

    answer = target_row["name"]
    formula = target_row["formula"]
    candidates = full_df[full_df["name"] != answer]["name"].drop_duplicates().tolist()

    if len(candidates) >= 3:
        distractors = random.sample(candidates, 3)
    else:
        distractors = candidates

    options = distractors + [answer]
    random.shuffle(options)

    st.session_state.math_quiz_data = {
        "formula": formula,
        "answer": answer,
        "options": options,
        "solved": False,
        "selected": None,
    }

# ==========================================
# 4. 사이드바
# ==========================================
st.sidebar.title("🛠️ 학습 설정")
menu = st.sidebar.radio(
    "메뉴 이동",
    [
        "📖 단어 학습장", "📝 맞춤형 어휘 테스트", "📖 AI 구문 분석 튜터",
        "🧮 수학 공식 플래시카드", "🧮 수학 공식 맞추기 퀴즈",
    ]
)

selected_file = None

if menu in ("📖 단어 학습장", "📝 맞춤형 어휘 테스트"):
    st.sidebar.divider()
    all_files = get_all_voca_files()

    if not all_files:
        st.sidebar.error("데이터 파일(.csv)이 없습니다.")
        st.error("단어장 CSV 파일을 먼저 업로드하거나 GitHub 저장소에 추가해주세요.")
        st.stop()

    selected_file = st.sidebar.selectbox("📖 단어장 선택", all_files)

# ==========================================
# 5. 단어 학습장 (플래시카드)
# ==========================================
if menu == "📖 단어 학습장":
    st.title("📖 영단어 데일리 학습장")
    st.markdown("**교재를 선택하고, 다 외운 단어는 체크해서 숨겨보세요.**")
    st.divider()

    df = load_selected_voca(selected_file)
    if df is None or df.empty:
        st.warning("사용할 수 있는 단어 데이터가 없습니다.")
        st.stop()

    if "memorized" not in st.session_state:
        st.session_state.memorized = set()

    days_list = sorted(df["day"].unique())
    selected_day = st.selectbox("📅 학습할 DAY를 선택하세요:", days_list)

    day_data = df[df["day"] == selected_day]
    total_words = len(day_data)

    memorized_count = sum(
        1 for index, row in day_data.iterrows()
        if f"{selected_file}_{selected_day}_{row['word']}_{index}" in st.session_state.memorized
    )

    st.write(f"전체 **{total_words}**개 중 **{memorized_count}**개 암기 완료!")
    st.progress(memorized_count / total_words if total_words > 0 else 0)

    if st.button("🔄 현재 DAY 암기 기록 초기화"):
        for index, row in day_data.iterrows():
            key = f"{selected_file}_{selected_day}_{row['word']}_{index}"
            if key in st.session_state.memorized:
                st.session_state.memorized.remove(key)
        st.rerun()

    st.write("")

    for index, row in day_data.iterrows():
        word = row["word"].strip()
        meaning = row["meaning"].strip()

        word_key = f"{selected_file}_{selected_day}_{word}_{index}"

        if word_key not in st.session_state.memorized:
            with st.expander(f"**{word}**"):
                st.success(f"💡 뜻: {meaning}")

                if st.button("✅ 다 외웠어요!", key=f"btn_{word_key}"):
                    st.session_state.memorized.add(word_key)
                    st.rerun()

    if memorized_count == total_words and total_words > 0:
        st.balloons()
        st.info("🎉 축하합니다! 이 DAY의 모든 단어를 완벽하게 암기했습니다.")

# ==========================================
# 6. 맞춤형 어휘 테스트
# ==========================================
elif menu == "📝 맞춤형 어휘 테스트":
    st.sidebar.divider()
    if st.sidebar.button("학습 기록 초기화"):
        reset_quiz_stats()
        if "quiz_data" in st.session_state:
            del st.session_state.quiz_data
        st.rerun()

    st.title("📝 맞춤형 어휘 테스트")

    if "total_count" not in st.session_state:
        reset_quiz_stats()

    df = load_selected_voca(selected_file)
    if df is None or df.empty:
        st.warning("사용할 수 있는 단어 데이터가 없습니다.")
        st.stop()

    day_list = sorted(df["day"].unique())
    selected_day = st.selectbox(
        f"📍 {selected_file} - 학습 범위를 선택하세요:",
        day_list
    )

    filtered_df = df[df["day"] == selected_day]

    if filtered_df.empty:
        st.warning("선택한 학습 범위에 단어가 없습니다.")
        st.stop()

    state_key = f"quiz_{selected_file}_{selected_day}"

    if (
        "current_state_key" not in st.session_state
        or st.session_state.current_state_key != state_key
    ):
        st.session_state.current_state_key = state_key
        if "quiz_data" in st.session_state:
            del st.session_state.quiz_data

    if "quiz_data" not in st.session_state:
        initialize_quiz(filtered_df, df)

    total = st.session_state.total_count
    correct = st.session_state.correct_count
    accuracy = round((correct / total) * 100, 1) if total else 0

    col1, col2, col3 = st.columns(3)
    col1.metric("푼 문제", total)
    col2.metric("정답 수", correct)
    col3.metric("정답률", f"{accuracy}%")

    quiz = st.session_state.quiz_data

    st.divider()
    st.subheader(f"Q. 다음 단어의 뜻은? : **{quiz['word']}**")

    cols = st.columns(2)

    for i, option in enumerate(quiz["options"]):
        disabled = quiz["solved"]

        if cols[i % 2].button(
            option,
            key=f"opt_{i}",
            use_container_width=True,
            disabled=disabled
        ):
            quiz["solved"] = True
            quiz["selected"] = option
            st.session_state.total_count += 1

            if option == quiz["answer"]:
                st.session_state.correct_count += 1
            else:
                st.session_state.wrong_words.append({
                    "word": quiz["word"],
                    "answer": quiz["answer"],
                    "selected": option,
                })

            st.rerun()

    if quiz["solved"]:
        if quiz["selected"] == quiz["answer"]:
            st.success("🎉 정답!")
        else:
            st.error(f"❌ 오답! 정답: {quiz['answer']}")

        if st.button("➡️ 다음 문제", type="primary"):
            del st.session_state.quiz_data
            st.rerun()

    if st.session_state.wrong_words:
        with st.expander("📌 오답 노트 보기"):
            wrong_df = pd.DataFrame(st.session_state.wrong_words)
            st.dataframe(
                wrong_df.rename(columns={
                    "word": "단어",
                    "answer": "정답",
                    "selected": "내가 고른 답"
                }),
                use_container_width=True
            )

# ==========================================
# 7. AI 구문 분석 튜터
# ==========================================
elif menu == "📖 AI 구문 분석 튜터":
    st.title("📖 AI 구문 분석 튜터")
    st.info("🚀 노량진 캠퍼스 전용 AI 분석 서버 가동 중")

    if client is None:
        st.error("API 키 설정에 문제가 있습니다. 관리자에게 문의하세요.")
        st.caption(f"오류 종류: {client_error}")
        st.stop()

    user_input = st.text_area(
        "분석할 영어 문장을 입력하세요:",
        height=150,
        max_chars=MAX_ANALYSIS_LENGTH
    )

    if st.button("🔍 전문 분석 시작"):
        if not user_input.strip():
            st.warning("분석할 영어 문장을 입력해주세요.")
            st.stop()

        prompt = f"""
다음 영어 문장을 학생이 이해하기 쉽게 분석해줘.

출력 형식:
1. 전체 문장 구조
2. 구문 분석
3. 직독직해
4. 자연스러운 해석
5. 핵심 문법 포인트
6. 시험에서 주의할 부분

문장:
{user_input}
"""

        with st.spinner("AI가 구문을 정밀 분석 중입니다..."):
            try:
                response = client.responses.create(model=MODEL_NAME, input=prompt)
                st.markdown("---")
                st.markdown(response.output_text)

            except Exception as e:
                error_message = str(e)
                # 실제 오류 원인은 Streamlit Cloud의 Manage app 로그에서 확인
                print(f"[AI 구문 분석 오류] {type(e).__name__}: {error_message}", flush=True)

                if "429" in error_message:
                    st.warning("⚠️ 현재 요청이 많습니다. 잠시 후 다시 시도해주세요.")
                elif "503" in error_message:
                    st.warning("⚠️ AI 서버가 일시적으로 혼잡합니다. 5~10초 뒤 다시 시도해주세요.")
                else:
                    st.error("분석 중 오류가 발생했습니다. 관리자에게 문의하세요.")
                    st.caption(f"오류 종류: {type(e).__name__}")

# ==========================================
# 8. 수학 공식 플래시카드
# ==========================================
elif menu == "🧮 수학 공식 플래시카드":
    st.title("🧮 수학 공식 플래시카드")
    st.markdown("**단원을 선택하고, 공식 이름을 보면서 수식을 떠올려보세요.**")
    st.divider()

    math_df = load_math_formulas()
    if math_df is None or math_df.empty:
        st.warning(f"'{MATH_FORMULAS_FILE}' 파일이 없거나 비어 있습니다.")
        st.stop()

    if "math_memorized" not in st.session_state:
        st.session_state.math_memorized = set()

    math_subjects = get_subjects_in_order(math_df)
    selected_subject = st.selectbox("📚 과목을 선택하세요:", math_subjects)

    subject_df = math_df[math_df["subject"] == selected_subject]
    math_categories = subject_df["category"].unique()
    selected_category = st.selectbox("📂 단원을 선택하세요:", math_categories)

    cat_data = subject_df[subject_df["category"] == selected_category]
    total_formulas = len(cat_data)

    memorized_count = sum(
        1 for index, row in cat_data.iterrows()
        if f"{selected_category}_{row['name']}_{index}" in st.session_state.math_memorized
    )

    st.write(f"전체 **{total_formulas}**개 중 **{memorized_count}**개 암기 완료!")
    st.progress(memorized_count / total_formulas if total_formulas > 0 else 0)

    if st.button("🔄 현재 단원 암기 기록 초기화"):
        for index, row in cat_data.iterrows():
            key = f"{selected_category}_{row['name']}_{index}"
            if key in st.session_state.math_memorized:
                st.session_state.math_memorized.remove(key)
        st.rerun()

    st.write("")

    for index, row in cat_data.iterrows():
        name = row["name"]
        formula = row["formula"]
        card_key = f"{selected_category}_{name}_{index}"

        if card_key not in st.session_state.math_memorized:
            with st.expander(f"**{name}**"):
                st.latex(formula)

                if st.button("✅ 다 외웠어요!", key=f"btn_math_{card_key}"):
                    st.session_state.math_memorized.add(card_key)
                    st.rerun()

    if memorized_count == total_formulas and total_formulas > 0:
        st.balloons()
        st.info("🎉 축하합니다! 이 단원의 모든 공식을 완벽하게 암기했습니다.")

# ==========================================
# 9. 수학 공식 맞추기 퀴즈
# ==========================================
elif menu == "🧮 수학 공식 맞추기 퀴즈":
    st.sidebar.divider()
    if st.sidebar.button("학습 기록 초기화", key="math_quiz_reset_sidebar"):
        reset_math_quiz_stats()
        if "math_quiz_data" in st.session_state:
            del st.session_state.math_quiz_data
        st.rerun()

    st.title("🧮 수학 공식 맞추기 퀴즈")
    st.markdown("**수식을 보고, 그게 어떤 공식인지 맞혀보세요.**")

    math_df = load_math_formulas()
    if math_df is None or math_df.empty:
        st.warning(f"'{MATH_FORMULAS_FILE}' 파일이 없거나 비어 있습니다.")
        st.stop()

    if "math_total_count" not in st.session_state:
        reset_math_quiz_stats()

    math_subjects = get_subjects_in_order(math_df)
    selected_subject = st.selectbox("📚 과목을 선택하세요:", math_subjects, key="math_quiz_subject")

    subject_df = math_df[math_df["subject"] == selected_subject]
    math_categories = subject_df["category"].unique()
    selected_category = st.selectbox("📂 단원을 선택하세요:", math_categories, key="math_quiz_category")

    cat_data = subject_df[subject_df["category"] == selected_category]

    if cat_data.empty:
        st.warning("선택한 단원에 공식이 없습니다.")
        st.stop()

    state_key = f"mathquiz_{selected_subject}_{selected_category}"

    if (
        "math_current_state_key" not in st.session_state
        or st.session_state.math_current_state_key != state_key
    ):
        st.session_state.math_current_state_key = state_key
        if "math_quiz_data" in st.session_state:
            del st.session_state.math_quiz_data

    if "math_quiz_data" not in st.session_state:
        initialize_math_quiz(cat_data, subject_df)

    total = st.session_state.math_total_count
    correct = st.session_state.math_correct_count
    accuracy = round((correct / total) * 100, 1) if total else 0

    col1, col2, col3 = st.columns(3)
    col1.metric("푼 문제", total)
    col2.metric("정답 수", correct)
    col3.metric("정답률", f"{accuracy}%")

    quiz = st.session_state.math_quiz_data

    st.divider()
    st.subheader("Q. 다음은 어떤 공식인가요?")
    st.latex(quiz["formula"])

    cols = st.columns(2)

    for i, option in enumerate(quiz["options"]):
        disabled = quiz["solved"]

        if cols[i % 2].button(
            option,
            key=f"mathopt_{i}",
            use_container_width=True,
            disabled=disabled
        ):
            quiz["solved"] = True
            quiz["selected"] = option
            st.session_state.math_total_count += 1

            if option == quiz["answer"]:
                st.session_state.math_correct_count += 1
            else:
                st.session_state.math_wrong_items.append({
                    "formula": quiz["formula"],
                    "answer": quiz["answer"],
                    "selected": option,
                })

            st.rerun()

    if quiz["solved"]:
        if quiz["selected"] == quiz["answer"]:
            st.success("🎉 정답!")
        else:
            st.error(f"❌ 오답! 정답: {quiz['answer']}")

        if st.button("➡️ 다음 문제", type="primary", key="math_next"):
            del st.session_state.math_quiz_data
            st.rerun()

    if st.session_state.math_wrong_items:
        with st.expander("📌 오답 노트 보기"):
            for item in reversed(st.session_state.math_wrong_items):
                st.latex(item["formula"])
                st.write(f"정답: **{item['answer']}**  /  내가 고른 답: {item['selected']}")
                st.divider()
