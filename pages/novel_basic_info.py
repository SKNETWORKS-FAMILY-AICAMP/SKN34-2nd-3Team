import streamlit as st
import pandas as pd
import os
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any

# ==========================================
# 1. 데이터 모델 (Data Models)
# ==========================================
@dataclass
class Novel:
    novel_id: int
    url: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    cover_image_url: Optional[str] = None
    is_free: Optional[bool] = None

@dataclass
class NovelStatistics:
    novel_id: int
    view_count: Optional[int] = 0
    favorite_count: Optional[int] = 0
    like_count: Optional[int] = 0
    total_episode_count: Optional[int] = 0
    free_episode_count: Optional[int] = 0
    char_count: Optional[int] = 0

@dataclass
class NovelAuthor:
    novel_id: int
    author_name: str
    role: str

@dataclass
class NovelGroup:
    novel_id: int
    group_name: str

@dataclass
class NovelGenre:
    novel_id: int
    genre_type: str
    genre_name: str

@dataclass
class NovelTag:
    novel_id: int
    tag_id: Optional[int]
    tag_name: str

@dataclass
class Tag:
    tag_id: int
    tag_name: str

@dataclass
class Episode:
    episode_id: int
    novel_id: int
    episode_num: int
    title: str
    views: Optional[int] = 0
    likes: Optional[int] = 0
    comments: Optional[int] = 0
    is_free: Optional[int] = 1
    created_at: Optional[str] = None

@dataclass
class Comment:
    comment_id: int
    episode_id: int
    parent_comment_id: Optional[int]
    content: str
    likes: Optional[int] = 0
    created_at: Optional[str] = None

# ==========================================
# 2. 레포지토리 계층 (Repository)
# ==========================================
class NovelRepository(ABC):
    @abstractmethod
    def get_novel(self, novel_id: int) -> Optional[Novel]: pass
    @abstractmethod
    def get_novel_statistics(self, novel_id: int) -> Optional[NovelStatistics]: pass
    @abstractmethod
    def get_novel_authors(self, novel_id: int) -> List[NovelAuthor]: pass
    @abstractmethod
    def get_novel_group(self, novel_id: int) -> Optional[NovelGroup]: pass
    @abstractmethod
    def get_novel_genres(self, novel_id: int) -> List[NovelGenre]: pass
    @abstractmethod
    def get_novel_tags(self, novel_id: int) -> List[NovelTag]: pass
    @abstractmethod
    def get_tags(self, novel_id: int) -> List[Tag]: pass
    @abstractmethod
    def get_episodes(self, novel_id: int) -> List[Episode]: pass
    @abstractmethod
    def get_comments(self, novel_id: int) -> List[Comment]: pass
    @abstractmethod
    def set_novel(self, novel: Novel) -> None: pass

class SampleNovelRepository(NovelRepository):
    def __init__(self, data_dir: str = "./db/data"):
        self.data_dir = data_dir
        self.memory_store_novel: Dict[int, Novel] = {}
        
        self.df_works = self._load_csv("works.csv")       
        self.df_episodes = self._load_csv("episodes.csv")
        self.df_comments = self._load_csv("comments.csv")

    def _load_csv(self, filename: str) -> pd.DataFrame:
        path = os.path.join(self.data_dir, filename)
        if os.path.exists(path):
            try: return pd.read_csv(path)
            except Exception as e: st.sidebar.error(f"'{filename}' 읽기 실패: {e}")
        return pd.DataFrame()

    def _get_work_row(self, novel_id: int) -> Optional[Dict]:
        if self.df_works.empty or 'work_id' not in self.df_works.columns: return None
        row_df = self.df_works[self.df_works['work_id'] == novel_id]
        if row_df.empty: return None
        return row_df.iloc[0].to_dict()

    def get_novel(self, novel_id: int) -> Optional[Novel]:
        if novel_id in self.memory_store_novel:
            return self.memory_store_novel[novel_id]
        row = self._get_work_row(novel_id)
        if not row: return None
        return Novel(
            novel_id=row.get('work_id'),
            url=row.get('source_url'),
            title=row.get('title', '정보 없음'),
            description=row.get('introduction', '정보 없음'),
            cover_image_url=row.get('cover_url'),
            is_free=row.get('free', None)
        )

    def set_novel(self, novel: Novel) -> None:
        self.memory_store_novel[novel.novel_id] = novel

    def get_novel_statistics(self, novel_id: int) -> Optional[NovelStatistics]:
        row = self._get_work_row(novel_id)
        if not row: return None
        return NovelStatistics(
            novel_id=novel_id,
            view_count=row.get('view_count', 0),
            favorite_count=row.get('preference_count', 0),
            like_count=row.get('like_count', 0),
            total_episode_count=row.get('chapter_count', 0),
            free_episode_count=row.get('free_chapter_count', 0),
            char_count=row.get('characters', 0)
        )

    def get_novel_authors(self, novel_id: int) -> List[NovelAuthor]:
        row = self._get_work_row(novel_id)
        if not row: return []
        authors = []
        # 백엔드(데이터) 쪽에서는 'role'을 무조건 채워줌 (에러 방지)
        if pd.notna(row.get('author_name')):
            authors.append(NovelAuthor(novel_id, str(row['author_name']), '작가'))
        if pd.notna(row.get('illustrator_name')):
            authors.append(NovelAuthor(novel_id, str(row['illustrator_name']), '일러스트레이터'))
        return authors

    def get_novel_group(self, novel_id: int) -> Optional[NovelGroup]:
        row = self._get_work_row(novel_id)
        if not row or pd.isna(row.get('group_name')): return None
        return NovelGroup(novel_id, str(row['group_name']))

    def get_novel_genres(self, novel_id: int) -> List[NovelGenre]:
        row = self._get_work_row(novel_id)
        if not row: return []
        genres = []
        # 백엔드(데이터)쪽에서는 '1차', '2차'를 채워줌
        if pd.notna(row.get('genre_best_name')):
            genres.append(NovelGenre(novel_id, '1차', str(row['genre_best_name'])))
        if pd.notna(row.get('genres_json')):
            try:
                clean_json = str(row['genres_json']).replace('""', '"')
                genre_list = eval(clean_json) if clean_json.startswith('[') else []
                for g in genre_list:
                    genres.append(NovelGenre(novel_id, '2차', str(g)))
            except: pass
        return genres

    def get_novel_tags(self, novel_id: int) -> List[NovelTag]:
        row = self._get_work_row(novel_id)
        if not row or pd.isna(row.get('tags_json')): return []
        tags = []
        try:
            clean_json = str(row['tags_json']).replace('""', '"')
            tag_list = eval(clean_json) if clean_json.startswith('[') else []
            for t in tag_list:
                tags.append(NovelTag(novel_id, None, str(t)))
        except: pass
        return tags

    def get_tags(self, novel_id: int) -> List[Tag]: return []

    def get_episodes(self, novel_id: int) -> List[Episode]:
        if self.df_episodes.empty or 'work_id' not in self.df_episodes.columns: return []
        ep_rows = self.df_episodes[self.df_episodes['work_id'] == novel_id].sort_values(by='episode_number')
        return [
            Episode(
                episode_id=r.get('episode_id', idx),
                novel_id=novel_id,
                episode_num=r.get('episode_number', 0),
                title=r.get('episode_title', '제목 없음'),
                views=r.get('view_count', 0),
                likes=r.get('like_count', 0),
                comments=r.get('comment_count', 0),
                is_free=1 if r.get('access_type') == 'FREE' else 0,
                created_at=str(r.get('published_at', ''))
            ) for idx, r in ep_rows.iterrows()
        ]

    def get_comments(self, novel_id: int) -> List[Comment]:
        if self.df_comments.empty or 'work_id' not in self.df_comments.columns: return []
        cm_rows = self.df_comments[self.df_comments['work_id'] == novel_id]
        return [
            Comment(
                comment_id=r.get('comment_id', idx),
                episode_id=r.get('episode_id', 0),
                parent_comment_id=r.get('parent_comment_id') if pd.notna(r.get('parent_comment_id')) else None,
                content=r.get('comment_text', ''),
                likes=r.get('like_count', 0),
                created_at=str(r.get('created_at', ''))
            ) for idx, r in cm_rows.iterrows()
        ]


# ==========================================
# 3. 서비스 계층
# ==========================================
class NovelBasicInfoService:
    def __init__(self, repository: NovelRepository):
        self.repository = repository

    def _validate_id(self, novel_id: int):
        if novel_id <= 0: raise ValueError("소설 ID는 0보다 커야 합니다.")

    def get_novel(self, novel_id: int) -> Optional[Novel]:
        self._validate_id(novel_id); return self.repository.get_novel(novel_id)
    def get_novel_statistics(self, novel_id: int) -> Optional[NovelStatistics]:
        self._validate_id(novel_id); return self.repository.get_novel_statistics(novel_id)
    def get_novel_authors(self, novel_id: int) -> List[NovelAuthor]:
        self._validate_id(novel_id); return self.repository.get_novel_authors(novel_id)
    def get_novel_group(self, novel_id: int) -> Optional[NovelGroup]:
        self._validate_id(novel_id); return self.repository.get_novel_group(novel_id)
    def get_novel_genres(self, novel_id: int) -> List[NovelGenre]:
        self._validate_id(novel_id); return self.repository.get_novel_genres(novel_id)
    def get_novel_tags(self, novel_id: int) -> List[NovelTag]:
        self._validate_id(novel_id); return self.repository.get_novel_tags(novel_id)
    def get_episodes(self, novel_id: int) -> List[Episode]:
        self._validate_id(novel_id); return self.repository.get_episodes(novel_id)
    def get_comments(self, novel_id: int) -> List[Comment]:
        self._validate_id(novel_id); return self.repository.get_comments(novel_id)
    def set_novel(self, novel: Novel) -> None:
        self._validate_id(novel.novel_id); self.repository.set_novel(novel)


# ==========================================
# 4. 프레젠테이션 계층 (UI)
# ==========================================
def render_page():
    st.set_page_config(page_title="소설 기본정보 조회", layout="wide")
    st.title("📖 소설 상세정보 조회 시스템")
    
    repository = SampleNovelRepository(data_dir="./db/data") 
    service = NovelBasicInfoService(repository)
    
    novel_id_input = st.text_input("🔍 조회할 소설 ID를 입력하세요:", "")
    
    if st.button("조회"):
        if not novel_id_input:
            st.warning("소설 ID를 입력해 주세요.")
            return
        if not novel_id_input.isdigit():
            st.error("소설 ID는 숫자만 입력 가능합니다.")
            return
            
        novel_id = int(novel_id_input)
        
        try:
            novel = service.get_novel(novel_id)
            if not novel:
                st.error(f"❌ 해당 소설을 찾을 수 없습니다. (ID: {novel_id})")
                return
                
            st.markdown("---")
            
            # [영역 1] 작품 기본 정보, 작가, 그룹, 장르, 태그
            col_img, col_info = st.columns([1, 4])
            with col_img:
                if novel.cover_image_url:
                    st.image(novel.cover_image_url, width=150)
            
            with col_info:
                st.header(f"📘 {novel.title}")
                st.write(f"**소설 ID:** {novel.novel_id} | **유료 연재 여부:** {'무료' if novel.is_free else '유료'}")
                
                # 작가, 그룹 가져오기
                authors = service.get_novel_authors(novel_id)
                author_str = ", ".join([a.author_name if a.role == '작가' else f"{a.author_name}({a.role})" for a in authors]) if authors else "정보 없음"
                
                group = service.get_novel_group(novel_id)
                group_str = group.group_name if group else "정보 없음"
                st.write(f"**작가:** {author_str} | **작품 그룹:** {group_str}")
                
                # 장르, 태그 가져오기
                genres = service.get_novel_genres(novel_id)
                genre_str = ", ".join([g.genre_name for g in genres]) if genres else "장르 없음"
                
                tags = service.get_novel_tags(novel_id)
                tag_str = ", ".join([f"#{t.tag_name}" for t in tags]) if tags else "태그 없음"
                
                st.markdown(f"**장르:** {genre_str}")
                st.markdown(f"**태그:** {tag_str}")
                st.write(f"**작품 소개:** {novel.description}")
                
                if novel.url: st.markdown(f"🔗 [작품 원본 링크]({novel.url})")
            
            # [영역 2] 통계 정보
            stats = service.get_novel_statistics(novel_id)
            if stats:
                st.markdown("---")
                st.subheader("📊 작품 통계")
                col1, col2, col3, col4, col5 = st.columns(5)
                col1.metric("총 조회수", f"{stats.view_count:,}")
                col2.metric("선호작 수", f"{stats.favorite_count:,}")
                col3.metric("총 좋아요", f"{stats.like_count:,}")
                col4.metric("전체 회차", f"{stats.total_episode_count:,}")
                col5.metric("무료 회차", f"{stats.free_episode_count:,}")
            
            # [영역 3] 회차 목록
            episodes = service.get_episodes(novel_id)
            st.markdown("---")
            st.subheader(f"📚 회차 목록 (총 {len(episodes)}화)")
            if episodes:
                with st.expander("회차 데이터 자세히 보기"):
                    st.dataframe(pd.DataFrame([asdict(ep) for ep in episodes]), use_container_width=True)
            else:
                st.info("빈 목록 (해당 작품의 회차 데이터가 없습니다.)")
                
            # [영역 4] 댓글 목록
            comments = service.get_comments(novel_id)
            st.markdown("---")
            st.subheader(f"💬 댓글 목록 (총 {len(comments)}개)")
            if comments:
                with st.expander("댓글 데이터 자세히 보기"):
                    st.dataframe(pd.DataFrame([asdict(cm) for cm in comments]), use_container_width=True)
            else:
                st.info("빈 목록 (해당 작품에 달린 댓글이 없습니다.)")
                
        except ValueError as ve:
            st.error(f"입력 오류: {ve}")
        except Exception as e:
            st.error(f"시스템 오류 발생: {e}")

if __name__ == "__main__":
    render_page()