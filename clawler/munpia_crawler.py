import os
import sys
import csv
import json
import asyncio
import aiohttp
from datetime import datetime

# ==========================================
# 1. 설정 및 상수
# ==========================================
START_ID = 1
END_ID = 550000
CONCURRENCY_LIMIT = 80     # 동시 요청 제한수 (너무 높이면 429 에러 발생)
DELAY_BETWEEN_REQS = 0.01  # API 요청 간 지연 시간(초)
DATA_DIR = "db/data"

class OrderedCSVManager:
    """순차 저장을 보장하는 버퍼 기반 비동기 CSV 매니저"""
    def __init__(self, data_dir, start_id):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        self.lock = asyncio.Lock()
        
        self.files = {
            "works": os.path.join(data_dir, "works.csv"),
            "episodes": os.path.join(data_dir, "episodes.csv"),
            "comments": os.path.join(data_dir, "comments.csv"),
            "genres": os.path.join(data_dir, "genres.csv"),
            "tags": os.path.join(data_dir, "tags.csv"),
            "status_log": os.path.join(data_dir, "status_log.csv")
        }
        
        self.headers = {
            "works": ["work_id", "source_url", "title", "author_name", "illustrator_name", "introduction", "cover_url", "origin_cover_url", "group_name", "genres_json", "tags_json", "genre_best_name", "genre_best_code", "free", "paid_serial", "exclusive", "pre_exclusive", "adult", "contest", "rental", "pause", "finish", "epub", "ebook", "cp_novel", "view_count", "preference_count", "like_count", "chapter_count", "free_chapter_count", "characters", "created_at", "updated_at", "paid_conversion_open_at", "isbn", "period", "unit_type", "male_count", "female_count", "age_10s_percent", "age_20s_percent", "age_30s_percent", "age_40s_percent", "age_50s_percent", "notice_count", "notices_json", "events_json", "collected_at"],
            "episodes": ["work_id", "episode_id", "episode_number", "episode_title", "published_at", "access_type", "view_count", "like_count", "comment_count", "page_count", "adult", "paid_conversion_before_entry", "up", "collected_at", "source_url"],
            "comments": ["work_id", "episode_id", "comment_id", "parent_comment_id", "reply_level", "content_type", "comment_text", "like_count", "dislike_count", "created_at", "secret", "report_status", "block_status", "collected_at"],
            "genres": ["genre_name", "genre_best_code", "genre_best_name", "first_seen_work_id", "collected_at"],
            "tags": ["tag_id", "tag_name", "first_seen_work_id", "collected_at"],
            "status_log": ["candidate_work_id", "source_url", "http_status", "parse_status", "failure_type", "attempt_count", "last_attempt_at", "accepted"]
        }
        self._init_files_sync()
        
        # 캐시 및 순차 제어 변수
        self.seen_genres = self._load_existing_keys("genres", "genre_name")
        self.seen_tags = self._load_existing_keys("tags", "tag_id")
        self.processed_works = self._load_existing_keys("status_log", "candidate_work_id")
        
        self.buffer = {}              # 수집 완료된 결과를 담는 임시 딕셔너리
        self.expected_id = start_id   # 다음으로 저장해야 할 순번
        self._advance_expected_id()   # 이미 저장된 번호 건너뛰기

    def _init_files_sync(self):
        for key, path in self.files.items():
            if not os.path.exists(path):
                with open(path, 'w', encoding='utf-8-sig', newline='') as f:
                    csv.writer(f).writerow(self.headers[key])

    def _load_existing_keys(self, file_key, column_name):
        keys = set()
        path = self.files[file_key]
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                if column_name in reader.fieldnames:
                    for row in reader:
                        val = row[column_name]
                        keys.add(int(val) if val.isdigit() else val)
        return keys

    def _advance_expected_id(self):
        """저장해야 할 다음 번호(expected_id)가 이미 처리된 번호라면 스킵"""
        while self.expected_id in self.processed_works:
            self.expected_id += 1

    async def push_result(self, work_id, result_data):
        """워커가 수집한 결과를 버퍼에 넣고, 순서가 맞으면 CSV에 기록"""
        async with self.lock:
            self.buffer[work_id] = result_data
            
            # expected_id가 버퍼에 도착했다면 즉시 파일에 쓰고 다음 순번 확인
            while self.expected_id in self.buffer:
                data = self.buffer.pop(self.expected_id)
                self._write_to_csv(data)
                
                # 순서대로 로그 출력
                if data['type'] == 'SUCCESS':
                    print(f"✅ [순차저장] 작품 {self.expected_id} | 회차: {len(data['episodes'])}개 | 댓글: {len(data['comments'])}개")
                else:
                    fail_reason = data['log']['failure_type']
                    print(f"❌ [순차저장] 작품 {self.expected_id} | 실패/비공개: {fail_reason}")
                
                self.processed_works.add(self.expected_id)
                self.expected_id += 1
                self._advance_expected_id()

    def _write_to_csv(self, data):
        """실제 CSV 파일에 Append 기록"""
        # 성공 시 메타/회차/댓글/장르/태그 기록
        if data['type'] == 'SUCCESS':
            with open(self.files["works"], 'a', encoding='utf-8-sig', newline='') as f:
                csv.DictWriter(f, fieldnames=self.headers["works"]).writerow(data['work'])
            
            if data['episodes']:
                with open(self.files["episodes"], 'a', encoding='utf-8-sig', newline='') as f:
                    csv.DictWriter(f, fieldnames=self.headers["episodes"]).writerows(data['episodes'])
            
            if data['comments']:
                with open(self.files["comments"], 'a', encoding='utf-8-sig', newline='') as f:
                    csv.DictWriter(f, fieldnames=self.headers["comments"]).writerows(data['comments'])
                    
            if data['genres']:
                with open(self.files["genres"], 'a', encoding='utf-8-sig', newline='') as f:
                    writer = csv.writer(f)
                    for g in data['genres']:
                        if g[0] not in self.seen_genres:
                            writer.writerow(g)
                            self.seen_genres.add(g[0])
                            
            if data['tags']:
                with open(self.files["tags"], 'a', encoding='utf-8-sig', newline='') as f:
                    writer = csv.writer(f)
                    for t in data['tags']:
                        if t[0] not in self.seen_tags:
                            writer.writerow(t)
                            self.seen_tags.add(t[0])
                            
        # 성공/실패 여부 상관없이 Status Log 기록
        with open(self.files["status_log"], 'a', encoding='utf-8-sig', newline='') as f:
            csv.DictWriter(f, fieldnames=self.headers["status_log"]).writerow(data['log'])


class MunpiaAsyncCrawler:
    def __init__(self, db_manager):
        self.db = db_manager
        self.stop_event = asyncio.Event() 
        self.headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

    async def run(self):
        queue = asyncio.Queue()
        
        queued_count = 0
        for wid in range(START_ID, END_ID + 1):
            if wid not in self.db.processed_works:
                queue.put_nowait(wid)
                queued_count += 1
                
        print(f" 비동기 순차 수집 시작 (대기열: {queued_count}개 작품) | 동시성: {CONCURRENCY_LIMIT}")

        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(headers=self.headers, timeout=timeout) as session:
            workers = [
                asyncio.create_task(self.worker(queue, session))
                for _ in range(CONCURRENCY_LIMIT)
            ]
            
            await queue.join()
            for w in workers:
                w.cancel()

    async def worker(self, queue, session):
        while not self.stop_event.is_set():
            try:
                work_id = queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            try:
                # 데이터 수집 (성공/실패 Dictionary 반환)
                result = await self.process_single_work(work_id, session)
            except Exception as e:
                # 크래시 방지용 긴급 에러 반환
                result = {
                    'type': 'FAIL',
                    'log': {
                        "candidate_work_id": work_id, "source_url": f"https://www.munpia.com/novel/detail/{work_id}",
                        "http_status": "", "parse_status": "FAIL", "failure_type": f"FATAL_ERROR: {str(e)[:50]}",
                        "attempt_count": 1, "last_attempt_at": datetime.now().isoformat(), "accepted": "N"
                    }
                }
            
            # 수집 결과를 DB 매니저에 넘김 (순서 맞으면 쓰기, 아니면 버퍼 대기)
            await self.db.push_result(work_id, result)
            queue.task_done()
            
            # 부하 방지
            await asyncio.sleep(DELAY_BETWEEN_REQS)

    async def process_single_work(self, work_id, session):
        collected_at = datetime.now().isoformat()
        source_url = f"https://www.munpia.com/novel/detail/{work_id}"
        
        log_data = {
            "candidate_work_id": work_id, "source_url": source_url, 
            "http_status": "", "parse_status": "FAIL", "failure_type": "", 
            "attempt_count": 1, "last_attempt_at": collected_at, "accepted": "N"
        }

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
            
        except Exception as e:
            log_data["failure_type"] = f"WORK_EXCEPTION: {str(e)[:50]}"
            return {'type': 'FAIL', 'log': log_data}

        def parse_stat(val):
            return val if val is not None else ""

        genres = novel.get("genres", [])
        tags = novel.get("tags", [])
        genre_best_code = novel.get("genreBestCode", "")
        genre_best_name = novel.get("genreBestName", "")

        work_row = {
            "work_id": work_id, "source_url": source_url, "title": novel.get("title", ""),
            "author_name": novel.get("authorName", ""), "illustrator_name": novel.get("illustratorName", ""),
            "introduction": novel.get("introduction", ""), "cover_url": novel.get("coverUrl", ""),
            "origin_cover_url": novel.get("originCoverUrl", ""), "group_name": novel.get("groupName", ""),
            "genres_json": json.dumps(genres, ensure_ascii=False), "tags_json": json.dumps(tags, ensure_ascii=False),
            "genre_best_name": genre_best_name, "genre_best_code": genre_best_code,
            "free": novel.get("free", ""), "paid_serial": novel.get("paidSerial", ""),
            "exclusive": novel.get("exclusive", ""), "pre_exclusive": novel.get("preExclusive", ""),
            "adult": novel.get("adult", ""), "contest": novel.get("contest", ""),
            "rental": novel.get("rental", ""), "pause": novel.get("pause", ""), "finish": novel.get("finish", ""),
            "epub": novel.get("epub", ""), "ebook": novel.get("ebook", ""), "cp_novel": novel.get("cpNovel", ""),
            "view_count": parse_stat(novel.get("viewCount")), "preference_count": parse_stat(novel.get("preferenceCount")),
            "like_count": parse_stat(novel.get("likeCount")), "chapter_count": parse_stat(novel.get("chapterCount")),
            "free_chapter_count": parse_stat(novel.get("freeChapterCount")), "characters": parse_stat(novel.get("characters")),
            "created_at": novel.get("createdAt", ""), "updated_at": novel.get("updatedAt", ""),
            "paid_conversion_open_at": novel.get("paidConversionOpenAt", ""), "isbn": novel.get("isbn", ""),
            "period": novel.get("period", ""), "unit_type": novel.get("unitType", ""),
            "male_count": "", "female_count": "", "age_10s_percent": "", "age_20s_percent": "",
            "age_30s_percent": "", "age_40s_percent": "", "age_50s_percent": "",
            "notice_count": result.get("noticeInfo", {}).get("count", 0),
            "notices_json": json.dumps(result.get("noticeInfo", {}).get("list", []), ensure_ascii=False),
            "events_json": json.dumps(result.get("events", []), ensure_ascii=False),
            "collected_at": collected_at
        }

        genres_data = [[g, genre_best_code, genre_best_name, work_id, collected_at] for g in genres]
        tags_data = [[t.get("id"), t.get("title"), work_id, collected_at] for t in tags if t.get("id")]

        episodes_data = []
        comments_data = []
        
        try:
            page = 1
            while True:
                if self.stop_event.is_set(): break
                
                ep_url = f"https://www.munpia.com/api/v1/pc/novel-detail/{work_id}/chapters?order=ENTRY_FIRST&page={page}&size=100"
                async with session.get(ep_url) as ep_res:
                    if ep_res.status != 200: break
                    ep_data = await ep_res.json()
                    
                if ep_data.get("code") != "M000_00000": break
                
                ch_list = ep_data.get("result", {}).get("list", [])
                if not ch_list: break

                for ch in ch_list:
                    ep_id = ch.get("id")
                    access_type = "FREE" if ch.get("free") else "PAID"
                    
                    episodes_data.append({
                        "work_id": work_id, "episode_id": ep_id, "episode_number": ch.get("num", ""),
                        "episode_title": ch.get("title", ""), "published_at": ch.get("createdAt", ""),
                        "access_type": access_type, "view_count": parse_stat(ch.get("viewCount")),
                        "like_count": parse_stat(ch.get("likeCount")), "comment_count": parse_stat(ch.get("commentCount")),
                        "page_count": parse_stat(ch.get("pages")), "adult": ch.get("adult", ""),
                        "paid_conversion_before_entry": ch.get("paidConversionBeforeEntry", ""),
                        "up": ch.get("up", ""), "collected_at": collected_at, "source_url": source_url
                    })

                    if access_type == "FREE":
                        comms = await self.fetch_comments(session, work_id, ep_id, collected_at)
                        comments_data.extend(comms)

                if len(ch_list) < 100: break
                page += 1
                await asyncio.sleep(0.3)
                
        except Exception as e:
            log_data["failure_type"] = f"EPISODE_EXCEPTION: {str(e)[:50]}"
            return {'type': 'FAIL', 'log': log_data}

        log_data["parse_status"] = "SUCCESS"
        log_data["accepted"] = "Y"
        
        return {
            'type': 'SUCCESS', 'work': work_row, 'episodes': episodes_data, 
            'comments': comments_data, 'genres': genres_data, 'tags': tags_data, 'log': log_data
        }

    async def fetch_comments(self, session, work_id, episode_id, collected_at):
        c_page = 1
        c_data = []
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
                parent_id = c.get("parentId")
                c_data.append({
                    "work_id": work_id, "episode_id": episode_id, "comment_id": c.get("id", ""),
                    "parent_comment_id": "" if parent_id == 0 else parent_id,
                    "reply_level": c.get("replyLevel", ""), "content_type": c.get("contentType", ""),
                    "comment_text": c.get("content", ""), "like_count": c.get("likeCount", ""),
                    "dislike_count": c.get("dislikeCount", ""), "created_at": c.get("createdAt", ""),
                    "secret": c.get("secret", ""), "report_status": c.get("report", ""),
                    "block_status": c.get("block", ""), "collected_at": collected_at
                })
                
            if c_page >= c_result.get("totalPages", 1): break
            c_page += 1
            await asyncio.sleep(0.1)
            
        return c_data

if __name__ == "__main__":
    factory = asyncio.SelectorEventLoop if sys.platform == 'win32' else None
    
    db_manager = OrderedCSVManager(DATA_DIR, START_ID)
    crawler = MunpiaAsyncCrawler(db_manager)
    
    try:
        asyncio.run(crawler.run(), loop_factory=factory)
    except KeyboardInterrupt:
        print("\n⏹️ 수동으로 중단되었습니다.")