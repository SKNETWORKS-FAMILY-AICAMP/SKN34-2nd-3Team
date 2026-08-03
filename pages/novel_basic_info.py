import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

import streamlit as st
import pandas as pd
from dataclasses import asdict

from service.novel_service import NovelService
from service.novel_service_errors import NovelServiceError
from repository.novel_repository import CsvNovelRepository

def render_page():
    st.set_page_config(page_title="소설 기본정보 조회", layout="wide")
    st.title("📖 소설 상세정보 조회 시스템")

    try:
        repository = CsvNovelRepository(
            works_csv_path="./db/data/works.csv",
            authors_csv_path="./db/data/authors.csv",
            episodes_csv_path="./db/data/episodes.csv",
            comments_csv_path="./db/data/comments.csv"
        )
        # Service는 이제 CSV 경로를 모릅니다! Repository만 압니다.
        service = NovelService(repository=repository)
    except Exception as e:
        st.error(f"서비스 초기화에 실패했습니다: {e}")
        return
    
    user_input = st.text_input("🔍 조회할 소설 ID 또는 작품 URL을 입력하세요:", "")
    
    if st.button("조회"):
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
            
            # [영역 1] 작품 기본 정보
            col_img, col_info = st.columns([1, 4])
            with col_img:
                if novel.origin_cover_url:
                    st.image(novel.origin_cover_url, width=150)
            
            with col_info:
                st.header(f"📘 {novel.title}")
                st.write(f"**소설 ID:** {novel.novel_id} | **유료 연재 여부:** {'무료' if novel.free else '유료'}")
                
                # 작가 정보 조회 (entity/novel_author.py 규격 매핑)
                author = service.get_author(novel_id)
                if author:
                    author_str = f"{author.author_name}(일러스트레이터)" if author.is_illustrator else author.author_name
                else:
                    author_str = "정보 없음"
                
                st.write(f"**작가:** {author_str}")
                st.write(f"**작품 소개:** {novel.introduction if novel.introduction else '정보 없음'}")
                
                if novel.source_url: 
                    st.markdown(f"🔗 [작품 원본 링크]({novel.source_url})")
            
            # [영역 2] 통계 정보 (entity/novel_statistics.py 규격 매핑)
            stats = service.get_novel_statistics(novel_id)
            if stats:
                st.markdown("---")
                st.subheader("📊 작품 통계")
                col1, col2, col3 = st.columns(3)
                col1.metric("총 조회수", f"{stats.view_count:,}" if stats.view_count is not None else "0")
                col2.metric("선호작 수", f"{stats.preference_count:,}" if stats.preference_count is not None else "0")
                col3.metric("총 회차", f"{stats.chapter_count:,}" if stats.chapter_count is not None else "0")
            
            # [영역 3] 회차 목록 (entity/episode.py 규격 매핑)
            episodes = service.get_episodes(novel_id)
            st.markdown("---")
            st.subheader(f"📚 회차 목록 (총 {len(episodes)}화)")
            if episodes:
                with st.expander("회차 데이터 자세히 보기"):
                    ep_df = pd.DataFrame([asdict(ep) for ep in episodes])
                    st.dataframe(ep_df, use_container_width=True)
            else:
                st.info("빈 목록 (해당 작품의 회차 데이터가 없습니다.)")
                
            # [영역 4] 댓글 목록 (entity/comment.py 규격 매핑)
            comments = service.get_comments(novel_id)
            st.markdown("---")
            st.subheader(f"💬 댓글 목록 (총 {len(comments)}개)")
            if comments:
                with st.expander("댓글 데이터 자세히 보기"):
                    cm_df = pd.DataFrame([asdict(cm) for cm in comments])
                    st.dataframe(cm_df, use_container_width=True)
            else:
                st.info("빈 목록 (해당 작품에 달린 댓글이 없습니다.)")
                
        # 5. 예외 처리 (팀 컨벤션인 NovelServiceError 우선 처리)
        except NovelServiceError as nse:
            st.error(f"⚠️ {nse}")
        except Exception as e:
            st.error(f"시스템 오류 발생: {e}")

if __name__ == "__main__":
    render_page()