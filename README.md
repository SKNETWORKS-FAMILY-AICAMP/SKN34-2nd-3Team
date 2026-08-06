## SKN34-1st-2Team

# 웹소설 분석 및 유료 전환 추천 플랫폼

## 👥 팀 소개


| 윤성호                                                                                                                                                                    | 전진환                                                                                                                                                                | 김현지                                                                                                                                                              | 최대원                                                                                                                                                                |
| :----------------------------------------------------------------------------------------------------------------------------------------------------------------------: | :------------------------------------------------------------------------------------------------------------------------------------------------------------------: | :----------------------------------------------------------------------------------------------------------------------------------------------------------------: | ------------------------------------------------------------------------------------------------------------------------------------------------------------------: |
| PM<br>Architecting                                                                                                                                                     | Data Collecting<br> Data Preprocessing                                                                                                                             | Model Trading<br>                                                                                                                                                | DB<br>                                                                                                                                                             |
| <a href="https://github.com/Seongho-haru"><img src="https://img.shields.io/badge/GitHub-100000?style=for-the-badge&logo=github&logoColor=white" alt="윤성호 GitHub"/></a> | <a href="https://github.com/dfs32dfs"><img src="https://img.shields.io/badge/GitHub-100000?style=for-the-badge&logo=github&logoColor=white" alt="전진환 GitHub"/></a> | <a href="https://github.com/HJK013"><img src="https://img.shields.io/badge/GitHub-100000?style=for-the-badge&logo=github&logoColor=white" alt="김현지 GitHub"/></a> | <a href="https://github.com/wind1484"><img src="https://img.shields.io/badge/GitHub-100000?style=for-the-badge&logo=github&logoColor=white" alt="최대원 GitHub"/></a> |


## 📋 프로젝트 개요

> 개발 기간 : 2026.07.21 - 2026.08.06 

### 1. 프로젝트명

문피아 웹소설 분석 및 유료 전환 추천 플랫폼 (편집부 분석 서비스)

### 2. 프로젝트 소개

- 문피아 공개 작품·회차 데이터를 기반으로, 편집부 분석 사용자가 무료 작품 중 유료 전환 검토 후보를 탐색하고 반응 감소 작품을 식별할 수 있도록 지원하는 AI 기반 의사결정 지원 대시보드
- 유료 전환 시 예상되는 수익성과 타깃 점수를 산정하여, 객관적인 작품 수익화 여부 결정 지원
- 회차별 독자 이탈률 분석 및 키워드 기반 댓글 감성(긍정/부정/중립) 분류 시각화를 통한 독자 반응 확인

### 3. 프로젝트 필요성

- 웹소설 시장에서 무료 회차에서 유료 회차로 전환하는 작품 대상을 선택하는 것은 매출에 직결되는 핵심이지만, 기존에는 주관적인 예상에 의존하여 작품을 선별해야 했음
- 객관적인 데이터(회차별 조회수를 기반으로 한 이탈률, 조회/좋아요/댓글수와 댓글 감성과 같은 독자 반응, 장르, 성별·연령대 비중 등)를 기반으로 한 예측 모델을 통해 편집자가 최종 의사결정을 내릴 수 있는 근거를 제공

### 4. 프로젝트 목표

- 무료 연재작 대상 유료 전환 타깃 점수 산정 및 전환 후보군 추천
- 문피아 작품 URL 또는 ID 입력을 통한 작품별 상세정보 및 시각화 분석 화면 구성
- 머신러닝 기반 유료 전환 예측 모델을 활용한 데이터 기반 예상 조회수 및 낙폭치 시각화
- 회차별 독자 이탈 구간 및 댓글 감성(긍정/부정/중립) 시각화

## 🧰 기술 스택


| 구분               | 기술                                                                                                                                                                                                                                                                                                                                  |
| :---------------- | :----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Language         | ![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)                                                                                                                                                                                                                       |
| Web UI           | ![Streamlit 1.60.0](https://img.shields.io/badge/Streamlit-1.60.0-FF4B4B?style=flat-square&logo=streamlit&logoColor=white) ![Streamlit Extras 1.6.0](https://img.shields.io/badge/Streamlit_Extras-1.6.0-FF4B4B?style=flat-square&logo=streamlit&logoColor=white)                                                                   |
| Machine Learning | ![scikit-learn 1.9.0](https://img.shields.io/badge/scikit--learn-1.9.0-F7931E?style=flat-square&logo=scikitlearn&logoColor=white) ![PyTorch 2.13.0](https://img.shields.io/badge/PyTorch-2.13.0-EE4C2C?style=flat-square&logo=pytorch&logoColor=white) ![XGBoost](https://img.shields.io/badge/XGBoost-ML-189FDD?style=flat-square) |
| Database         | ![MySQL 8.4](https://img.shields.io/badge/MySQL-8.4-4479A1?style=flat-square&logo=mysql&logoColor=white)                                                                                                                                                                                                                            |
| Dataset          | ![Hugging Face Hub 1.26.0](https://img.shields.io/badge/Hugging_Face_Hub-1.26.0-FFD21E?style=flat-square&logo=huggingface&logoColor=black) ![CSV](https://img.shields.io/badge/CSV-Data-217346?style=flat-square&logo=files&logoColor=white)                                                                                        |
| Infrastructure   | ![Docker Compose](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat-square&logo=docker&logoColor=white)                                                                                                                                                                                                                 |


## 🗂️ 폴더 구조

```
SKN34-2nd-3Team/
├── clawler/
│   └── munpia_crawler.py      # 문피아 작품 및 회차 데이터 수집
├── db/
│   ├── data/                  # 원본 CSV 데이터 저장
│   └── migration/             # DB 스키마 생성 및 마이그레이션 SQL
├── docs/                      # 프로젝트 문서 및 이미지
├── entity/                    # 계층 간 데이터 전달 객체
├── pages/                     # Streamlit 멀티페이지 화면
├── repository/
│   ├── __init__.py
│   └── repository.py          # DB 연결 및 쿼리 실행
├── research/                  # 머신러닝 모델 실험 및 노트북
├── scripts/                   # 데이터 처리 및 모델 학습 스크립트
├── service/                   # 핵심 비즈니스 로직
├── .env.example               # 환경 변수 설정 예시
├── .gitignore
├── bootstrap.py               # 데이터 다운로드 및 DB 초기화
├── docker-compose.yml         # MySQL 컨테이너 구성
├── main.py                    # Streamlit 애플리케이션 진입점
├── README.md
└── requirements.txt
```

## ⚙️ ERD

![erd](./docs/erd.png) 

## 📰 데이터 정보

- [문피아 사이트](https://www.munpia.com/)
- [허깅 페이스 데이터 다운로드](https://huggingface.co/datasets/SKN34/SKN34-2nd-3Team)

> 문피아에 직접 연락하여 데이터 제공을 요청했으나 거절당했습니다. 
>
> 이후 데이터 수집 전 문피아의 `robots.txt`를 확인했으며, `/novel/detail/` 경로의 크롤링이 허용된 범위에서 작품 및 회차 데이터를 직접 수집했습니다. 수집한 데이터는 위 Hugging Face 데이터셋에서 다운로드할 수 있습니다.
>
> ```
> Allow: /novel/detail/
> ```
## 프로젝트 분석 이슈 및 트러블슈팅
| 구분         | 트러블 이슈                                                                                                 | 관련 GitHub Issue                                                              |
| ---------- | ------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------- |
| 데이터 수집     | 문피아에서 과거 시점별 누적 데이터를 제공하지 않아 연속적인 누적 데이터 수집은 불가능하고, 수집 시점의 스냅샷 데이터만 확보할 수 있었다.                         | [#7](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-2nd-3Team/issues/7)   |
| 데이터 단위     | 수집 데이터는 개인 독자의 열람·구매 이력이 아니라 작품·회차별로 합산된 그룹 데이터이므로 개인 독자의 실제 이탈을 분석할 수 없었다.                            | [#3](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-2nd-3Team/issues/3)   |
| 데이터 변경     | 데이터를 수정하거나 보완하기 위해 다시 수집할 때 기존 공개 작품·회차가 비공개로 전환되거나 삭제되어 이전 데이터와 최신 데이터가 일치하지 않는 문제가 발생했다.추            | [#36](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-2nd-3Team/issues/36) |
| 유료화 이력 누락  | 크롤링 당시 작품의 현재 무료·유료 상태만 수집해 무료 작품이 언제 유료로 전환됐는지에 대한 과거 이력을 충분히 확보하지 못했으며, 유료 전환 학습용 정답 데이터를 구성하기 어려웠다. | [#3](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-2nd-3Team/issues/3)   |
| 무료→유료 전환   | 무료 연재가 유료로 전환되면 첫 유료 회차 조회수가 새로 집계되어 마지막 무료 회차와 연속되지 않으므로 일반적인 회차 조회수 추세로 분석할 수 없었다.                   | [#3](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-2nd-3Team/issues/3)   |
| 후보 특징 추출   | 무료 작품의 유료 전환 후보를 찾기 위해 지도학습·비지도학습을 모두 실험했지만 작품별 특징이 대부분 비슷해 현재 데이터로는 안정적인 후보군 분리가 불가능했다.               | [#5](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-2nd-3Team/issues/5)   |
| 이탈률 점수 왜곡  | 조회수가 0이거나 매우 적은 상태로 오래 연재된 작품이 조회수 규모보다 낮은 변화율·이탈률을 중심으로 평가되면서 실제 성과와 달리 높은 점수를 받는 문제가 발생했다.           | [#41](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-2nd-3Team/issues/41) |
| 대용량 데이터 배포 | 대용량 원본 데이터를 Git LFS로 관리하려 했지만 실제 LFS 객체 다운로드가 불가능해 GitHub 저장소에서 분리하고 Hugging Face Dataset으로 이전했다.      | [#9](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-2nd-3Team/issues/9)   |
| 감소율 모델 선정 | 감소율 예측을 위한 딥러닝·머신러닝 모델 중 특정 모델이 압도적으로 높은 설명력이나 정확도를 보이지 않아 최적 모델 선정에 어려움을 겪었다. 딥러닝 활성화 함수로 ReLU, LeakyReLU, GELU, SiLU를 각각 적용해 비교했지만 뚜렷한 최적 모델을 찾지 못해, 최종적으로 오차율이 가장 낮은 머신러닝 Random Forest 모델을 선택했다. | — |
| 감정분석 대상 정책 통일 | 전체 댓글 중 감정분석 결과가 없는 댓글을 모두 신규 분석 대상으로 처리하면 작가 댓글과 대댓글까지 포함되는 문제가 있었다. 최초 학습 데이터 생성 기준과 동일하게 무료 회차의 텍스트 형식 독자 원댓글만 분석하도록 필터 기준을 통일했다. | — |
| 감정분석 모델 실사용 검증 | 파인튜닝 모델의 라벨 순서와 실제 출력 확률을 검증했다. 명확한 긍정·부정 문장은 정상적으로 분류했지만 중립 표현을 긍정으로 판단하는 사례를 발견했으며, 중립 데이터 보강과 임계값 조정이 필요한 개선 사항으로 정리했다. | — |



## 📌 수행결과



## ✏️ 향후 개선 계획

- NLP 감성 분석 고도화
  - 키워드 기반 감성 분류를 KoBERT 등의 사전학습 모델 기반 파인튜닝으로 업그레이드하여 웹소설 특유의 반어법 및 맥락 정밀 분석
  - 중립 댓글 오분류를 줄이기 위해 중립·경계 사례 데이터 보강
  - 작품·장르별 데이터 편중을 줄이고 작품 단위로 학습·검증 데이터 분리
  - 낮은 신뢰도와 오분류 댓글을 재검수하여 재학습 데이터로 활용
  - 정확도뿐 아니라 클래스별 F1-score와 혼동행렬을 활용한 성능 평가
  - 신규 댓글만 최신 모델로 분석하고 기존 분석 결과는 유지하면서 모델 버전 관리
- 데이터 분석 LLM 해석 기능
  - 기존 계획에는 LLM을 연동해 상단 지표를 해석하는 단계가 포함되어 있었으나 개발 일정상 구현하지 못했다. 편집자가 지표를 쉽게 이해할 수 있도록 AI가 핵심 지표의 의미와 분석 결과를 자연어로 풀어 설명하는 기능 추가
- 실시간 리스크 알림 서비스 연동
  - 관리 필요 작품군에서 특정 회차 이탈률이 급증할 경우 담당자에게 슬랙(Slack) 경고 알림을 전송하는 리스크 관리 기능 추가

## 실행 방법

#### 1. venv 가상환경 준비

- [`docs/01. 환경세팅.md`](./docs/01.%20환경세팅.md)의 **venv 가상환경 세팅**을 따라 가상환경을 생성하고 활성화한 뒤 필요한 패키지를 설치합니다.

#### 2. 애플리케이션 데이터 준비

- `.env.example`을 참고하여 프로젝트 루트에 `.env`를 준비한 뒤 다음 명령을 실행합니다.

```bash
python bootstrap.py
```

- `bootstrap.py`는 Hugging Face 데이터셋 다운로드, MySQL 실행, 데이터베이스 마이그레이션 및 데이터 적재, 추천 지표 계산과 모델 학습을 순서대로 수행합니다.

#### 3. 애플리케이션 실행

```bash
streamlit run main.py
```

## 💭 한 줄 회고

> 윤성호  
> 이번 프로젝트를 진행하며 GitHub의 프로젝트, 이슈, 포크, PR 등 다양한 기능을 직접 활용해 협업하는 과정을 경험할 수 있어서 뜻깊었다. 다만 이슈 작성 기준과 PR 템플릿이 미리 정해져 있지 않아 작업 내용을 공유하고 관리하는 과정에서 다소 아쉬움이 있었다. 또한 업무를 분배할 때 프론트엔드, 백엔드, DB, AI 모델 학습 및 연구, 데이터 수집처럼 역할과 책임을 명확히 구분하지 않고 모듈별 구현과 연구 작업을 중심으로 나누다 보니, 팀원들의 작업이 겹치거나 일부 업무가 원활하게 진행되지 못했다. 다음 프로젝트에서는 협업 규칙과 업무 영역을 초기에 명확히 정한다면 더욱 체계적이고 효율적으로 프로젝트를 진행할 수 있을 것 같다.

> 전진환  
> 이번 프로젝트에서는 웹소설 데이터를 직접 수집하고 전처리한 뒤, 댓글 감정분석 모델을 파인튜닝해 실제 서비스에 적용하는 작업을 담당했다. 처음에는 방대한 데이터와 예상보다 많은 오류 때문에 막막하기도 했지만, 하나씩 문제를 해결하고 결과가 화면에 실제로 반영되는 모습을 보며 큰 성취감을 느꼈다. 특히 단순히 모델을 만드는 것보다 데이터의 상태를 꼼꼼히 확인하고, 팀원들과 계속 의견을 맞춰 가는 과정이 중요하다는 점을 배울 수 있었다. 짧은 기간 안에 여러 작업을 동시에 진행해 아쉬움도 남았지만, 시행착오를 겪으며 끝까지 기능을 완성해 낸 경험 자체가 의미 있었고, 다음 프로젝트에서는 이번에 부족했던 부분을 보완해 더 완성도 있게 진행해 보고 싶다.

> 김현지  
> 조회수 예측을 위한 머신러닝과 딥러닝 모델을 연구하고 다양한 모델과 옵션을 조합해 최적의 모델을 찾는 작업에서 많은 시행착오를 겪었지만, 그 과정을 통해 배운 점이 많았던 프로젝트였다. 특히 실제 사이트에서 추출한 웹소설 데이터를 다뤄 Streamlit 웹 대시보드로 시각화하여 편집부의 의사결정을 돕는 서비스로 완성해 보며, 데이터 분석과 서비스 개발의 과정을 보다 더 잘 이해하게 되었다.

> 최대원  
> 이번 프로젝트에 관해 팀원들과 의견을 나누고 목표를 정하는 등 유익한 시간이 되었다.  
> 특히 데이터를 크롤링하고 분석하고 재정리하는 과정은 도움이 되었다. 다만, 정제되지 않은 데이터를 기반으로 타깃을 주제에 맞게 설정하는 과정과 문자를 분석해서 영향력을 넣으려는 과정이 어려웠다. 하물며 머신러닝과 딥러닝으로 모델 비교에서 정확도까지 떨어져 아쉬움이 남는다. 개인적으론 상업성을 목표로 만들어 봤다는 것에서 좋은 경험이 되었다.



