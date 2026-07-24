import streamlit as st
import google.generativeai as genai
import pandas as pd
import random
import os

st.set_page_config(
    page_title="김영편입 노량진 - 종합 학습 플랫폼",
    page_icon="🚀",
    layout="wide"
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
# 2. AI 설정
# ==========================================
try:
    GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
    genai.configure(api_key=GOOGLE_API_KEY)
    model = genai.GenerativeModel("gemini-2.5-flash")
except Exception:
    model = None

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
# 4. 사이드바
# ==========================================
st.sidebar.title("🛠️ 학습 설정")
menu = st.sidebar.radio(
    "메뉴 이동",
    ["📖 단어 학습장", "📝 맞춤형 어휘 테스트", "📖 AI 구문 분석 튜터"]
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

    if model is None:
        st.error("API 키 설정에 문제가 있습니다. 관리자에게 문의하세요.")
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
                response = model.generate_content(prompt)
                st.markdown("---")
                st.markdown(response.text)

            except Exception as e:
                error_message = str(e)

                if "429" in error_message:
                    st.warning("⚠️ 현재 요청이 많습니다. 잠시 후 다시 시도해주세요.")
                elif "503" in error_message:
                    st.warning("⚠️ 구글 AI 서버가 일시적으로 혼잡합니다. 5~10초 뒤 다시 시도해주세요.")
                else:
                    st.error("분석 중 오류가 발생했습니다. 관리자에게 문의하세요.")
