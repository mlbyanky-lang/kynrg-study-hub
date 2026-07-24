# 김영편입 노량진 - 종합 학습 플랫폼

`daily-voca`(단어 학습장)와 `ai-tutor-system`(어휘 테스트 + AI 구문 분석)을 하나로 통합한 Streamlit 앱입니다.

## 메뉴
- 📖 단어 학습장 — 교재/DAY 선택 후 플래시카드로 암기, 진도율 표시
- 📝 맞춤형 어휘 테스트 — 4지선다 퀴즈, 오답노트
- 📖 AI 구문 분석 튜터 — Gemini API로 영어 문장 구조 분석

## 데이터 형식
`.csv` 파일에 `day,word,meaning` 헤더가 있어야 합니다. 저장소 루트에 있는 모든 `.csv` 파일이 자동으로 단어장 선택 목록에 표시됩니다.

## 배포 설정 (Streamlit Cloud secrets)
```
APP_PASSWORD = "수강생 인증 코드"
GOOGLE_API_KEY = "Gemini API 키"
```
