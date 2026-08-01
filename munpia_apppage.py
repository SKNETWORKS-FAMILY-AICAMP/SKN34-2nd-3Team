import streamlit as st
import asyncio
import aiohttp
import json
import re
import sqlite3
import pandas as pd
from datetime import datetime
from abc import ABC, abstractmethod

# ==========================================
# 1. DB 추상화 및 구현체
# ==========================================
class AbstractDBManager(ABC):
    @abstractmethod
    async def push_result(self, work_id: int, result_data: dict):
        pass

class SQLiteManager(AbstractDBManager):
    def __init__(self, db_path="munpia_data.db"):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)

    async def push_result(self, work_id: int, result_data: dict):
        if result_data.get('type') == 'SUCCESS':
            df_work = pd.DataFrame([result_data['work']])
            df_work.to_sql('works', self.conn, if_exists='append', index=False)
            
            if result_data['episodes']:
                df_episodes = pd.DataFrame(result_data['episodes'])
                df_episodes.to_sql('episodes', self.conn, if_exists='append', index=False)
                
            if result_data['comments']:
                df_comments = pd.DataFrame(result_data['comments'])
                df_comments.to_sql('comments', self.conn, if_exists='append', index=False)
                
        df_log = pd.DataFrame([result_data['log']])
        df_log.to_sql('status_log', self.conn, if_exists='append', index=False)

# ==========================================
# 2. 크롤러 로직 (실시간 로그 콜백 추가)
# ==========================================
class SingleMunpiaCrawler:
    def __init__(self, db_manager: AbstractDBManager, status_cb=None):
        self.db = db_manager
        self.status_cb = status_cb
        self.stop_event = asyncio.Event()
        self.headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        self.semaphore = asyncio.Semaphore(20) 

    def _log(self, message: str):
        if self.status_cb:
            self.status_cb(message)

    async def crawl_and_save(self, work_id: int):
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(headers=self.headers, timeout=timeout) as session:
            try:
                result = await self.process_single_work(work_id, session)
                await self.db.push_result(work_id, result)
                return result
            except Exception as e:
                error_result = {
                    'type': 'FAIL',
                    'log': {
                        "candidate_work_id": work_id, 
                        "source_url": f"https://www.munpia.com/novel/detail/{work_id}",
                        "http_status": "", "parse_status": "FAIL", 
                        "failure_type": f"FATAL_ERROR: {str(e)[:50]}",
                        "attempt_count": 1, "last_attempt_at": datetime.now().isoformat(), 
                        "accepted": "N"
                    }
                }
                await self.db.push_result(work_id, error_result)
                return error_result

    async def process_single_work(self, work_id, session):
        collected_at = datetime.now().isoformat()
        source_url = f"https://www.munpia.com/novel/detail/{work_id}"
        
        log_data = {
            "candidate_work_id": work_id, "source_url": source_url, 
            "http_status": "", "parse_status": "FAIL", "failure_type": "", 
            "attempt_count": 1, "last_attempt_at": collected_at, "accepted": "N"
        }

        self._log(f"🔍 [작품 정보] 작품 ID ({work_id}) 기본 데이터 조회 시작...")
        
        # 1. 작품 상세 정보 수집 (생략 없이 기존과 동일)
        try:
            url = f"https://www.munpia.com/api/v1/pc/novel-detail/{work_id}"
            async with session.get(url) as res:
                log_data["http_status"] = res.status
                if res.status in (403, 429):
                    self.stop_event.set()
                    log_data["failure_type"] = f"HTTP_{res.status}_BLOCKED"
                    return {'type': 'FAIL', 'log': log_data}
                    
                if res.status != 200:
                    log_data["failure_type"] = f"HTTP_{res.status}"
                    return {'type': 'FAIL', 'log': log_data}

                data = await res.json()
                
            if data.get("code") != "M000_00000" or not data.get("result"):
                log_data["failure_type"] = data.get("message", "NOT_FOUND_OR_PRIVATE")
                return {'type': 'FAIL', 'log': log_data}

            result = data["result"]
            novel = result.get("novelInfo", {})
            self._log(f"📖 [작품 정보] 제목: **'{novel.get('title', '')}'** 확인 완료")
            
        except Exception as e:
            log_data["failure_type"] = f"WORK_EXCEPTION: {str(e)[:50]}"
            return {'type': 'FAIL', 'log': log_data}

        # 2. 작품 독자 통계 정보
        stats_data = {}
        try:
            stat_url = f"https://www.munpia.com/api/v1/pc/novel-detail/{work_id}/read-statistics"
            async with session.get(stat_url) as stat_res:
                if stat_res.status == 200:
                    stat_json = await stat_res.json()
                    if stat_json.get("code") == "M000_00000" and stat_json.get("result"):
                        stats_data = stat_json["result"]
        except Exception:
            pass

        def parse_stat(val):
            return val if val is not None else ""

        work_row = {
            "work_id": work_id, "source_url": source_url, "title": novel.get("title", ""),
            "author_name": novel.get("authorName", ""), "introduction": novel.get("introduction", ""),
            "genres_json": json.dumps(novel.get("genres", []), ensure_ascii=False), 
            "tags_json": json.dumps(novel.get("tags", []), ensure_ascii=False),
            "view_count": parse_stat(novel.get("viewCount")), "preference_count": parse_stat(novel.get("preferenceCount")),
            "chapter_count": parse_stat(novel.get("chapterCount")), "collected_at": collected_at,
            "crawl_status": "SUCCESS", "source_http_status": log_data["http_status"]
        }

        episodes_data = []
        comments_data = []
        comment_tasks = [] # 🔥 비동기 태스크를 담을 리스트
        
        # 3. 회차 목록 수집
        try:
            page = 1
            while True:
                if self.stop_event.is_set(): break
                self._log(f"📑 [회차 수집] 에피소드 목록 가져오는 중... (페이지: {page})")
                
                ep_url = f"https://www.munpia.com/api/v1/pc/novel-detail/{work_id}/chapters?order=ENTRY_FIRST&page={page}&size=100"
                async with session.get(ep_url) as ep_res:
                    if ep_res.status != 200: break
                    ep_data = await ep_res.json()
                    
                if ep_data.get("code") != "M000_00000": break
                
                ch_list = ep_data.get("result", {}).get("list", [])
                if not ch_list: break

                for ch in ch_list:
                    ep_id = ch.get("id")
                    ep_num = ch.get("num", "")
                    access_type = "FREE" if ch.get("free") else "PAID"
                    
                    episodes_data.append({
                        "work_id": work_id, "episode_id": ep_id, "episode_number": ep_num,
                        "episode_title": ch.get("title", ""), "published_at": ch.get("createdAt", ""),
                        "access_type": access_type, "view_count": parse_stat(ch.get("viewCount")),
                        "like_count": parse_stat(ch.get("likeCount")), "comment_count": parse_stat(ch.get("commentCount"))
                    })

                    # 🔥 하나씩 await 하지 않고 태스크 리스트에 추가만 함
                    if access_type == "FREE":
                        task = self.fetch_comments(session, work_id, ep_id, ep_num, collected_at)
                        comment_tasks.append(task)

                if len(ch_list) < 100: break
                page += 1
                await asyncio.sleep(0.3)
                
            # 4. 🔥 수집된 모든 댓글 태스크를 한 번에 비동기 실행 (병렬 처리)
            if comment_tasks:
                self._log(f"💬 [댓글 수집] 총 {len(comment_tasks)}개 회차의 댓글을 병렬로 수집합니다! 🚀")
                # gather를 통해 병렬로 던지고, 결과를 한 번에 받음
                results = await asyncio.gather(*comment_tasks, return_exceptions=True)
                
                # 결과 리스트 합치기
                for res in results:
                    if isinstance(res, list):  # 에러가 발생하지 않고 정상 리스트가 반환된 경우만
                        comments_data.extend(res)
                
        except Exception as e:
            log_data["failure_type"] = f"EPISODE_EXCEPTION: {str(e)[:50]}"
            return {'type': 'FAIL', 'log': log_data}

        log_data["parse_status"] = "SUCCESS"
        log_data["accepted"] = "Y"
        
        return {
            'type': 'SUCCESS', 'work': work_row, 'episodes': episodes_data, 
            'comments': comments_data, 'log': log_data
        }

    async def fetch_comments(self, session, work_id, episode_id, ep_num, collected_at):
        c_page = 1
        c_data = []
        
        # 🔥 세마포어를 통해 동시 실행 개수 제한 (서버 부하/차단 방지)
        async with self.semaphore:
            while True:
                if self.stop_event.is_set(): break
                c_url = f"https://www.munpia.com/api/v1/pc/novel-detail/{work_id}/entries/{episode_id}/comments?order=LATEST&page={c_page}&size=100"
                async with session.get(c_url) as c_res:
                    if c_res.status != 200: break
                    c_json = await c_res.json()
                    
                if c_json.get("code") != "M000_00000": break
                
                c_result = c_json.get("result", {})
                c_list = c_result.get("list", [])
                if not c_list: break
                    
                for c in c_list:
                    c_data.append({
                        "work_id": work_id, "episode_id": episode_id, "comment_id": c.get("id", ""),
                        "comment_text": c.get("content", ""), "like_count": c.get("likeCount", ""),
                        "created_at": c.get("createdAt", "")
                    })
                    
                if c_page >= c_result.get("totalPages", 1): break
                c_page += 1
                # 병렬로 돌기 때문에 여기서 딜레이를 많이 주지 않아도 됩니다.
                await asyncio.sleep(0.05) 
                
        return c_data
# ==========================================
# 3. Streamlit UI
# ==========================================
def extract_work_id(url_or_id: str) -> int:
    match = re.search(r'\d+', url_or_id)
    return int(match.group()) if match else None

def main():
    st.set_page_config(page_title="문피아 데이터 수집기", layout="wide")
    st.title("📚 문피아 작품 데이터 실시간 수집기")

    db_manager = SQLiteManager()
    
    target_input = st.text_input("작품 주소 또는 작품 ID 입력", placeholder="예: https://novel.munpia.com/12345")
    
    if st.button("수집 시작", type="primary"):
        if not target_input:
            st.warning("작품 주소나 ID를 입력해주세요.")
            return

        work_id = extract_work_id(target_input)
        if not work_id:
            st.error("올바른 작품 ID를 찾을 수 없습니다.")
            return

        # 실시간 진행 상황을 보여줄 Status 컨테이너 생성
        with st.status(f"작품 (ID: {work_id}) 수집 진행 중...", expanded=True) as status_box:
            
            # UI 접힌 박스 내부로 실시간 텍스트 출력하는 콜백
            def update_status_ui(msg):
                status_box.write(msg)

            crawler = SingleMunpiaCrawler(db_manager, status_cb=update_status_ui)
            
            # 비동기 실행
            result = asyncio.run(crawler.crawl_and_save(work_id))
            
            if result['type'] == 'SUCCESS':
                status_box.update(label="✅ 데이터 수집 및 DB 적재 완료!", state="complete", expanded=False)
                
                work_info = result['work']
                st.success(f"**[{work_info['title']}]** 수집 완료")
                
                col1, col2, col3 = st.columns(3)
                col1.metric("총 조회수", f"{work_info['view_count']:,}" if str(work_info['view_count']).isdigit() else work_info['view_count'])
                col2.metric("수집된 회차 수", f"{len(result['episodes'])} 개")
                col3.metric("수집된 댓글 수", f"{len(result['comments'])} 개")

                if result['episodes']:
                    st.subheader("📋 최근 회차 미리보기")
                    st.dataframe(pd.DataFrame(result['episodes']).head(5))
            else:
                status_box.update(label="❌ 수집 중 오류 발생", state="error", expanded=True)
                fail_reason = result['log'].get('failure_type', '알 수 없는 에러')
                st.error(f"실패 원인: {fail_reason}")

if __name__ == "__main__":
    main()