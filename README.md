# SKN34-2nd-3Team

애플리케이션의 영속성 계층은 `repository/repository.py`의 MySQL
`Repository` 하나로 통합되어 있습니다. 실행 중에는 CSV 파일을 직접 읽거나
수정하지 않습니다.

## 최초 데이터베이스 구성

1. `.env.example`을 참고하여 `.env`에 DB 접속 정보를 설정합니다.
2. 아래 CSV 파일을 `db/data`에 배치합니다.
   `tag.csv`, `novel_genre.csv`, `novel_author.csv`, `novel_group.csv`,
   `novel.csv`, `novel_tag.csv`, `episode.csv`, `novel_statistics.csv`,
   `novel_ai_evaluation.csv`, `comment.csv`
3. `docker compose up -d`를 실행합니다.

MySQL 컨테이너가 처음 생성될 때 `V1__create_initial_schema.sql`로 테이블을
생성하고 `V2__load_csv_data.sql`로 CSV 데이터를 DB에 적재합니다. MySQL의
초기화 스크립트는 빈 데이터 볼륨에서만 실행되므로 기존 볼륨에 V2를 다시
적용하려면 별도의 마이그레이션 실행이 필요합니다.
