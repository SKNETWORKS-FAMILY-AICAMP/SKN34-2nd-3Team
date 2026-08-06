-- V5: 댓글 감정분석 결과 테이블 생성 및 CSV 적재

DROP TABLE IF EXISTS comment_statistics_stage;

CREATE TABLE comment_statistics_stage (
    comment_id INT NOT NULL,
    novel_id INT NOT NULL,
    episode_id INT NOT NULL,
    predicted_label VARCHAR(20) NOT NULL,
    negative_score FLOAT NOT NULL,
    neutral_score FLOAT NOT NULL,
    positive_score FLOAT NOT NULL,
    confidence FLOAT NOT NULL,
    model_version VARCHAR(100) NOT NULL,
    comment_text_hash CHAR(64) NOT NULL,
    analyzed_at DATETIME NOT NULL,

    PRIMARY KEY (comment_id),

    CONSTRAINT chk_comment_statistics_stage_label
        CHECK (
            predicted_label IN (
                'negative',
                'neutral',
                'positive'
            )
        )
) ENGINE = InnoDB
  DEFAULT CHARACTER SET = utf8mb4
  COLLATE = utf8mb4_0900_ai_ci;

LOAD DATA INFILE
    '/var/lib/mysql-files/comment_ai_evaluation.csv'
INTO TABLE comment_statistics_stage
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(
    @comment_id,
    @novel_id,
    @episode_id,
    @predicted_label,
    @negative_score,
    @neutral_score,
    @positive_score,
    @confidence,
    @model_version,
    @comment_text_hash,
    @analyzed_at
)
SET
    comment_id = CAST(NULLIF(TRIM(@comment_id), '') AS UNSIGNED),
    novel_id = CAST(NULLIF(TRIM(@novel_id), '') AS UNSIGNED),
    episode_id = CAST(NULLIF(TRIM(@episode_id), '') AS UNSIGNED),
    predicted_label = LOWER(
        TRIM(BOTH '\r' FROM TRIM(@predicted_label))
    ),
    negative_score = CAST(
        NULLIF(TRIM(@negative_score), '') AS DECIMAL(10, 8)
    ),
    neutral_score = CAST(
        NULLIF(TRIM(@neutral_score), '') AS DECIMAL(10, 8)
    ),
    positive_score = CAST(
        NULLIF(TRIM(@positive_score), '') AS DECIMAL(10, 8)
    ),
    confidence = CAST(
        NULLIF(TRIM(@confidence), '') AS DECIMAL(10, 8)
    ),
    model_version = TRIM(
        BOTH '\r' FROM TRIM(@model_version)
    ),
    comment_text_hash = LOWER(
        TRIM(BOTH '\r' FROM TRIM(@comment_text_hash))
    ),
    analyzed_at = STR_TO_DATE(
        LEFT(
            TRIM(BOTH '\r' FROM TRIM(@analyzed_at)),
            19
        ),
        '%Y-%m-%dT%H:%i:%s'
    );

ALTER TABLE comment_statistics_stage
    ADD INDEX idx_comment_statistics_novel_label (
        novel_id,
        predicted_label
    ),
    ADD INDEX idx_comment_statistics_episode_label (
        episode_id,
        predicted_label
    ),
    ADD INDEX idx_comment_statistics_model_version (
        model_version
    ),
    ADD CONSTRAINT fk_comment_statistics_stage_comment
        FOREIGN KEY (comment_id)
        REFERENCES comment (comment_id)
        ON DELETE CASCADE,
    ADD CONSTRAINT fk_comment_statistics_stage_novel
        FOREIGN KEY (novel_id)
        REFERENCES novel (novel_id),
    ADD CONSTRAINT fk_comment_statistics_stage_episode
        FOREIGN KEY (episode_id)
        REFERENCES episode (episode_id);

RENAME TABLE
    comment_statistics_stage
TO
    comment_statistics;

SELECT
    COUNT(*) AS comment_statistics_row_count
FROM comment_statistics;

SELECT
    predicted_label,
    COUNT(*) AS label_count
FROM comment_statistics
GROUP BY predicted_label
ORDER BY predicted_label;
