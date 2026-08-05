import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

import streamlit as st
import pandas as pd
import altair as alt
from dataclasses import asdict

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
    should_search = False
    
    if is_clicked:
        should_search = True
        st.session_state.auto_searched = True 
    elif query_url and not st.session_state.auto_searched:
        should_search = True
        st.session_state.auto_searched = True

    if should_search:
        if not user_input.strip():
            st.warning("소설 ID 또는 작품 URL을 입력해 주세요.")
            return
            
        try:
            novel_id = service.parse_novel_id(user_input)
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


            st.markdown("---")
            st.subheader("📈 향후 조회수 예측 그래프")
            
            prediction_result = prediction_service.get_prediction_data(novel_id)
            
            if prediction_result is not None:
                pred_df, drop_rate = prediction_result
                
                if not pred_df.empty:
                    st.metric(
                        label="다음 화(예측 1화) 조회수 예상 낙폭",
                        value=f"-{drop_rate}%",
                        delta=f"최근 화 대비 {drop_rate}% 감소 예상",
                        delta_color="inverse"
                    )

                    chart = alt.Chart(pred_df).mark_line(point=True).encode(
                        x=alt.X("회차:Q", title="회차", scale=alt.Scale(zero=False)),
                        y=alt.Y("조회수:Q", title="조회수"),
                        color=alt.Color("구분:N", scale=alt.Scale(
                            range=["#1f77b4", "#ff7f0e"] 
                        )),
                        strokeDash=alt.condition(
                            alt.datum.구분 == "실제 조회수",
                            alt.value([0]),     
                            alt.value([5, 5])    
                        )
                    ).properties(height=400)
                    
                    st.altair_chart(chart, use_container_width=True)
                    
                    if novel.free:
                        st.info("💡 위 그래프는 수집된 전체 작품의 무료 -> 유료 전환 데이터를 분석하여 도출된 **실제 평균 낙폭치**를 바탕으로, 해당 작품이 유료로 전환되었을 때의 예상 조회수를 시뮬레이션한 결과입니다.")
                    else:
                        st.info("💡 위 그래프는 수집된 전체 유료 작품 데이터를 분석하여 도출된 **자연 감소율(유지율)**을 바탕으로 시뮬레이션한 결과입니다.")
                else:
                    st.info("그래프를 렌더링하기 위한 데이터가 부족합니다.")
            else:
                st.info("그래프를 렌더링하기 위한 회차 데이터가 없습니다.")

            episodes = service.get_episodes(novel_id)
            st.markdown("---")
            st.subheader(f"📚 회차 목록 (총 {len(episodes)}화)")
            if episodes:
                with st.expander("회차 데이터 자세히 보기"):
                    ep_df = pd.DataFrame([asdict(ep) for ep in episodes])
                    st.dataframe(ep_df, use_container_width=True)
            else:
                st.info("빈 목록 (해당 작품의 회차 데이터가 없습니다.)")
                
            comments = service.get_comments(novel_id)
            st.markdown("---")
            st.subheader(f"💬 댓글 목록 (총 {len(comments)}개)")
            if comments:
                with st.expander("댓글 데이터 자세히 보기"):
                    cm_df = pd.DataFrame([asdict(cm) for cm in comments])
                    st.dataframe(cm_df, use_container_width=True)
            else:
                st.info("빈 목록 (해당 작품에 달린 댓글이 없습니다.)")
                
        except NovelServiceError as nse:
            st.error(f"⚠️ {nse}")
        except Exception as e:
            st.error(f"시스템 오류 발생: {e}")

if __name__ == "__main__":
    render_page()
