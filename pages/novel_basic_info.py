import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

import streamlit as st
import pandas as pd
import altair as alt
from dataclasses import asdict

from streamlit_extras.card_selector import card_selector

from service.novel_service import NovelService
from service.novel_prediction_service import NovelPredictionService 
from service.novel_service_errors import NovelServiceError
from repository.repository import Repository

def render_page():
    st.set_page_config(page_title="소설 기본정보 조회", layout="wide")
    st.title("📖 소설 상세정보 조회 시스템")

    try:
        repository = Repository()
        service = NovelService(repository=repository)
        prediction_service = NovelPredictionService(repository=repository) 
    except Exception as e:
        st.error(f"서비스 초기화에 실패했습니다: {e}")
        return
    
    query_url = st.query_params.get("url", "")
    
    if "last_query_url" not in st.session_state or st.session_state.last_query_url != query_url:
        st.session_state.last_query_url = query_url
        st.session_state.input_url = query_url
        st.session_state.auto_searched = False 
        
    user_input = st.text_input(
        "🔍 조회할 소설 ID 또는 작품 URL을 입력하세요:", 
        key="input_url"
    )
    
    is_clicked = st.button("조회")
    
    if is_clicked:
        st.session_state.has_searched = True
        st.session_state.search_target = user_input
    elif query_url and not st.session_state.get("auto_searched", False):
        st.session_state.has_searched = True
        st.session_state.search_target = query_url
        st.session_state.auto_searched = True

    should_search = st.session_state.get("has_searched", False)

    if should_search:
        target_input = st.session_state.get("search_target", user_input)
        
        if not target_input.strip():
            st.warning("소설 ID 또는 작품 URL을 입력해 주세요.")
            st.session_state.has_searched = False
            return
            
        if "munpia.com/novel/detail/" in target_input:
            import re
            match = re.search(r'/detail/(\d+)', target_input)
            if match:
                target_input = match.group(1)
                
        try:
            with st.spinner(" 기본 작품 정보를 불러오는 중입니다..."):
                novel_id = service.parse_novel_id(target_input)
                novel = service.get_novel(novel_id)
                
                if not novel:
                    st.error(f"❌ 해당 소설을 찾을 수 없습니다. (ID: {novel_id})")
                    return
                    
                st.markdown("---")
                
                col_img, col_info = st.columns([1, 4])
                with col_img:
                    if novel.origin_cover_url:
                        st.image(novel.origin_cover_url, width=150)
                
                with col_info:
                    st.header(f"📘 {novel.title}")
                    st.write(f"**소설 ID:** {novel.novel_id} | **유료 연재 여부:** {'무료' if novel.free else '유료'}")
                    
                    author = service.get_author(novel_id)
                    if author:
                        author_str = f"{author.author_name}(일러스트레이터)" if author.is_illustrator else author.author_name
                    else:
                        author_str = "정보 없음"
                    
                    st.write(f"**작가:** {author_str}")
                    st.write(f"**작품 소개:** {novel.introduction if novel.introduction else '정보 없음'}")
                    
                    if novel.source_url: 
                        st.markdown(f"🔗 [작품 원본 링크]({novel.source_url})")

                stats = service.get_novel_statistics(novel_id)
                if stats:
                    st.markdown("---")
                    st.subheader("📊 작품 통계")
                    col1, col2, col3 = st.columns(3)
                    col1.metric("총 조회수", f"{stats.view_count:,}" if stats.view_count is not None else "0")
                    col2.metric("선호작 수", f"{stats.preference_count:,}" if stats.preference_count is not None else "0")
                    col3.metric("총 회차", f"{stats.chapter_count:,}" if stats.chapter_count is not None else "0")

                    st.markdown("##### 👥 독자 성별 및 연령대 비율")
                    stat_col1, stat_col2 = st.columns(2)
                    
                    with stat_col1:
                        raw_male = stats.male_count if stats.male_count is not None else 0
                        raw_female = stats.female_count if stats.female_count is not None else 0
                        total_gender = raw_male + raw_female
                        
                        if total_gender > 0:
                            male_pct = round((raw_male / total_gender) * 100, 1)
                            female_pct = round((raw_female / total_gender) * 100, 1)
                        else:
                            male_pct, female_pct = 50.0, 50.0

                        gender_df = pd.DataFrame({
                            '성별': ['남성', '여성'],
                            '비율': [male_pct, female_pct]
                        })
                        gender_chart = alt.Chart(gender_df).mark_arc(innerRadius=50).encode(
                            theta=alt.Theta(field="비율", type="quantitative"),
                            color=alt.Color(field="성별", type="nominal", scale=alt.Scale(range=["#1f77b4", "#ff7f0e"])),
                            tooltip=[alt.Tooltip('성별', title='성별'), alt.Tooltip('비율', title='비율 (%)', format='.1f')]
                        ).properties(title="성별 독자 비율", height=200)
                        st.altair_chart(gender_chart, width="stretch")

                    with stat_col2:
                        age_data = {
                            '연령대': ['10대', '20대', '30대', '40대', '50대 이상'],
                            '비율': [
                                stats.age_10s_percent or 0,
                                stats.age_20s_percent or 0,
                                stats.age_30s_percent or 0,
                                stats.age_40s_percent or 0,
                                stats.age_50s_percent or 0
                            ]
                        }
                        age_df = pd.DataFrame(age_data)
                        if age_df['비율'].sum() == 0:
                            age_df['비율'] = [20, 20, 20, 20, 20]
                        age_chart = alt.Chart(age_df).mark_bar().encode(
                            x=alt.X('연령대:N', sort=None, title=None, axis=alt.Axis(labelAngle=0)),
                            y=alt.Y('비율:Q', title=None),
                            color=alt.Color('연령대:N', legend=None),
                            tooltip=['연령대', '비율']
                        ).properties(title="연령대별 독자 비중", height=200)
                        st.altair_chart(age_chart, width="stretch")

            st.markdown("---")
            st.subheader("📈 향후 조회수 예측 시뮬레이션")
            
            selected_model = card_selector(
                [
                    dict(
                        icon=":material/smart_toy:",
                        title="AI 맞춤형 예측 (Random Forest)",
                        description="작품의 장르, 분량, 독자 반응 등을 분석해 정밀하게 예측합니다.",
                    ),
                    dict(
                        icon=":material/bar_chart:",
                        title="통계 기반 예측 (전체 평균)",
                        description="전체 작품의 평균 무료→유료 전환 낙폭을 적용한 수치를 노출합니다.",
                    ),
                ],
                key="prediction_model_selector",
            )
            
            is_ml_mode = True if selected_model == 0 or selected_model is None else False
            
            with st.spinner(" AI 예측 모델 및 그래프 데이터를 계산하는 중입니다..."):
                prediction_result = prediction_service.get_prediction_data(novel_id, is_ml=is_ml_mode)
                
                if prediction_result is not None:
                    pred_df, drop_rate = prediction_result
                    
                    if not pred_df.empty:
                        if not novel.free and '구분' in pred_df.columns:
                            episodes_raw = service.get_episodes(novel_id)
                            free_count = sum(1 for ep in episodes_raw if str(ep.access_type).strip().upper() == 'FREE')
                            if free_count == 0:
                                free_count = int(len(pred_df) * 0.3)
                            
                            def categorize_segment(row):
                                if row['구분'] == '실제 조회수':
                                    if row['회차'] <= free_count:
                                        return '실제 조회수 (무료 회차)'
                                    else:
                                        return '실제 조회수 (유료 회차)'
                                else:
                                    return '예상 조회수'
                            
                            pred_df['구분'] = pred_df.apply(categorize_segment, axis=1)
                            color_scale = alt.Scale(domain=['실제 조회수 (무료 회차)', '실제 조회수 (유료 회차)', '예상 조회수'], range=['#1f77b4', "#46c553", '#ff7f0e'])
                            dash_condition = alt.condition(alt.datum.구분 == '예상 조회수', alt.value([5, 5]), alt.value([0]))
                        else:
                            color_scale = alt.Scale(range=['#1f77b4', '#ff7f0e'])
                            dash_condition = alt.condition(alt.datum.구분 == '실제 조회수', alt.value([0]), alt.value([5, 5]))

                        st.metric(
                            label="다음 화(예측 1화) 조회수 예상 낙폭",
                            value=f"-{drop_rate}%",
                            delta=f"-{drop_rate}% (감소 예상)",
                            delta_color="normal"
                        )

                        chart = alt.Chart(pred_df).mark_line(point=True).encode(
                            x=alt.X("회차:Q", title="회차", scale=alt.Scale(zero=False)),
                            y=alt.Y("조회수:Q", title="조회수"),
                            color=alt.Color("구분:N", scale=color_scale),
                            strokeDash=dash_condition
                        ).properties(height=400)
                        
                        st.altair_chart(chart, width="stretch")
                        
                        if novel.free:
                            if is_ml_mode:
                                st.info("💡 위 그래프는 **Random Forest AI 모델**이 해당 작품의 특성(장르, 좋아요, 댓글 등)을 기반으로 분석하여 도출한 **맞춤형 유료 전환 시뮬레이션 결과**입니다.")
                            else:
                                st.info("💡 위 그래프는 수집된 전체 작품의 무료 -> 유료 전환 데이터를 분석하여 도출된 **전체 평균 낙폭치**를 바탕으로 시뮬레이션한 결과입니다.")
                        else:
                            st.info("💡 위 그래프는 수집된 전체 유료 작품 데이터를 분석하여 도출된 **자연 감소율(유지율)**을 바탕으로 시뮬레이션한 결과입니다.")
                        
                        st.caption("ℹ️ *본 시뮬레이션 모델은 ±12 내외의 오차율을 보일 수 있습니다.*")
                    else:
                        st.info("그래프를 렌더링하기 위한 데이터가 부족합니다.")
                else:
                    st.info("그래프를 렌더링하기 위한 회차 데이터가 없습니다.")

            st.markdown("---")
            st.subheader("📚 회차 및 댓글 상세 정보")
            
            with st.spinner(" 회차 및 댓글 상세 데이터를 불러오는 중입니다..."):
                col_ep, col_cm = st.columns([5.5, 4.5])
                
                episodes = service.get_episodes(novel_id)
                comments = service.get_comments(novel_id)
                
                if episodes:
                    ep_df = pd.DataFrame([asdict(ep) for ep in episodes])
                    
                    if 'published_at' in ep_df.columns:
                        ep_df['published_at'] = pd.to_datetime(ep_df['published_at']).dt.strftime('%Y-%m-%d')
                        
                    if 'access_type' in ep_df.columns:
                        ep_df['access_type'] = ep_df['access_type'].apply(
                            lambda x: '무료 회차' if str(x).strip().upper() == 'FREE' else '유료 회차'
                        )
                        
                    rename_cols = {
                        'episode_number': '회차 번호',
                        'episode_title': '회차 제목',
                        'published_at': '업로드일',
                        'access_type': '유료/무료',
                        'view_count': '조회수',
                        'like_count': '좋아요 수',
                        'comment_count': '댓글 수'
                    }
                    
                    rename_cols = {k: v for k, v in rename_cols.items() if k in ep_df.columns}
                    ep_df = ep_df.rename(columns=rename_cols)
                    
                    if '회차 번호' in ep_df.columns:
                        ep_df['회차 번호'] = pd.to_numeric(ep_df['회차 번호'], errors='coerce')
                        ep_df = ep_df.sort_values(by='회차 번호', ascending=True)
                    
                    display_cols = list(rename_cols.values())
                    ep_df_display = ep_df[display_cols]
                    
                    with col_ep:
                        st.markdown(f"**📖 전체 회차 목록 (총 {len(episodes)}화)**")
                        st.dataframe(ep_df_display, width="stretch", height=562, hide_index=True)
                else:
                    with col_ep:
                        st.info("해당 작품의 회차 데이터가 없습니다.")
                        ep_df_display = pd.DataFrame()

                with col_cm:
                    total_comments_official = 0
                    if not ep_df_display.empty and '댓글 수' in ep_df_display.columns:
                        total_comments_official = int(ep_df_display['댓글 수'].sum())
                    
                    st.markdown(f"**💬 회차별 댓글 목록 (전체 {total_comments_official}개)**")
                    
                    ep_numbers = ep_df_display['회차 번호'].tolist() if not ep_df_display.empty and '회차 번호' in ep_df_display.columns else []
                    
                    if ep_numbers:
                        options = ["전체 댓글"] + ep_numbers
                        
                        selected_option = st.selectbox(
                            "👇 댓글을 확인할 회차 번호를 선택하세요:", 
                            options, 
                            index=0
                        )
                        
                        cm_df = pd.DataFrame([asdict(cm) for cm in comments]) if comments else pd.DataFrame()
                        filtered_cm = pd.DataFrame()
                        
                        if not cm_df.empty:
                            if selected_option == "전체 댓글":
                                filtered_cm = cm_df.copy()
                            else:
                                str_selected_ep = str(selected_option).split('.')[0]
                                target_ep = None
                                
                                for ep in episodes:
                                    if str(ep.episode_number).split('.')[0] == str_selected_ep:
                                        target_ep = ep
                                        break
                                        
                                if target_ep and target_ep.episode_id:
                                    global_ep_id = str(target_ep.episode_id).split('.')[0].strip()
                                    
                                    if 'episode_id' in cm_df.columns:
                                        cm_df['clean_ep_id'] = cm_df['episode_id'].astype(str).str.split('.').str[0].str.strip()
                                        filtered_cm = cm_df[cm_df['clean_ep_id'] == global_ep_id].copy()
                        
                        if not filtered_cm.empty:
                            if selected_option == "전체 댓글":
                                st.success(f"전체 수집된 댓글 ({len(filtered_cm)}개)")
                            else:
                                st.success(f"{selected_option}화 수집된 댓글 ({len(filtered_cm)}개)")
                            
                            if 'created_at' in filtered_cm.columns:
                                filtered_cm['created_at'] = pd.to_datetime(filtered_cm['created_at']).dt.strftime('%Y-%m-%d')
                                
                            cm_rename_cols = {
                                'comment_text': '댓글 내용',
                                'like_count': '좋아요 수',
                                'dislike_count': '싫어요 수',
                                'created_at': '작성 시간'
                            }
                            
                            cm_rename_cols = {k: v for k, v in cm_rename_cols.items() if k in filtered_cm.columns}
                            filtered_cm = filtered_cm.rename(columns=cm_rename_cols)
                            
                            cm_display_cols = list(cm_rename_cols.values())
                            filtered_cm_display = filtered_cm[cm_display_cols]
                            
                            sort_option = st.radio(
                                "정렬",
                                ["과거순", "최신순", "좋아요순"],
                                horizontal=True,
                                label_visibility="collapsed"
                            )
                            
                            if sort_option == "과거순" and "작성 시간" in filtered_cm_display.columns:
                                filtered_cm_display = filtered_cm_display.sort_values(by="작성 시간", ascending=True)
                            elif sort_option == "최신순" and "작성 시간" in filtered_cm_display.columns:
                                filtered_cm_display = filtered_cm_display.sort_values(by="작성 시간", ascending=False)
                            elif sort_option == "좋아요순" and "좋아요 수" in filtered_cm_display.columns:
                                filtered_cm_display['좋아요 수'] = pd.to_numeric(filtered_cm_display['좋아요 수'], errors='coerce')
                                filtered_cm_display = filtered_cm_display.sort_values(by="좋아요 수", ascending=False)

                            st.dataframe(filtered_cm_display, width="stretch", height=350, hide_index=True)
                        else:
                            st.warning("⚠️ 해당 기준에 표시할 수집된 텍스트 데이터가 DB에 없습니다.")
                    else:
                        st.info("해당 작품에 연동할 회차 정보가 없습니다.")
                        
        except NovelServiceError as nse:
            st.error(f"⚠️ {nse}")
        except Exception as e:
            st.error(f"시스템 오류 발생: {e}")

if __name__ == "__main__":
    render_page()