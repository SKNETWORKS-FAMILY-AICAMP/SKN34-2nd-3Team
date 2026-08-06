-- Materialized recommendation metrics based on test.ipynb.
-- Episodes 1-25 and access-type transition edges are excluded. The reference
-- view count and FREE/PAID retention are stored as independent components.

SET NAMES utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS novel_recommendation_score (
    novel_id INT NOT NULL,
    view_scale_score DECIMAL(6, 2),
    free_retention_score DECIMAL(6, 2),
    paid_retention_score DECIMAL(6, 2),
    reference_view_count INT NOT NULL DEFAULT 0,
    view_scale_max INT NOT NULL DEFAULT 100000,
    view_grade VARCHAR(20) NOT NULL DEFAULT '아주 낮음',
    scored_episode_count INT NOT NULL,
    average_dropout_rate DECIMAL(8, 6) NOT NULL,
    calculated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (novel_id),
    CONSTRAINT fk_recommendation_score_novel
        FOREIGN KEY (novel_id) REFERENCES novel (novel_id)
) ENGINE=InnoDB DEFAULT CHARACTER SET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS novel_comment_sentiment (
    novel_id INT NOT NULL,
    positive_count INT NOT NULL DEFAULT 0,
    negative_count INT NOT NULL DEFAULT 0,
    neutral_count INT NOT NULL DEFAULT 0,
    total_count INT NOT NULL DEFAULT 0,
    calculated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (novel_id),
    CONSTRAINT fk_comment_sentiment_novel
        FOREIGN KEY (novel_id) REFERENCES novel (novel_id)
) ENGINE=InnoDB DEFAULT CHARACTER SET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

DELETE FROM novel_recommendation_score;

INSERT INTO novel_recommendation_score (
    novel_id, view_scale_score, free_retention_score, paid_retention_score,
    reference_view_count, view_scale_max, view_grade,
    scored_episode_count, average_dropout_rate, calculated_at
)
WITH ordered_episode AS (
    SELECT
        novel_id, episode_number, access_type, view_count, published_at,
        MAX(published_at) OVER (
            PARTITION BY novel_id
        ) AS latest_published_at,
        LAG(access_type) OVER (
            PARTITION BY novel_id ORDER BY episode_number, episode_id
        ) AS previous_access_type,
        LAG(view_count) OVER (
            PARTITION BY novel_id ORDER BY episode_number, episode_id
        ) AS previous_view_count
    FROM episode
),
eligible_episode AS (
    SELECT
        novel_id, access_type,
        CASE
            WHEN view_count = 0 THEN 1.0
            ELSE GREATEST(
                0.0,
                (previous_view_count - view_count) / previous_view_count
            )
        END AS dropout_rate
    FROM ordered_episode
    WHERE episode_number > 25
      AND access_type = previous_access_type
      AND (view_count = 0 OR previous_view_count > 0)
      AND view_count IS NOT NULL
      AND access_type IN ('FREE', 'PAID')
),
percentile_score AS (
    SELECT
        novel_id, access_type, dropout_rate,
        100.0 * (1.0 - PERCENT_RANK() OVER (
            PARTITION BY access_type ORDER BY dropout_rate
        )) AS episode_score
    FROM eligible_episode
),
retention_summary AS (
    SELECT
        novel_id,
        AVG(CASE WHEN access_type = 'FREE' THEN episode_score END) AS free_retention_score,
        AVG(CASE WHEN access_type = 'PAID' THEN episode_score END) AS paid_retention_score,
        COUNT(*) AS scored_episode_count,
        AVG(dropout_rate) AS average_dropout_rate
    FROM percentile_score
    GROUP BY novel_id
),
mature_episode AS (
    SELECT
        novel_id,
        view_count,
        ROW_NUMBER() OVER (
            PARTITION BY novel_id
            ORDER BY published_at DESC, episode_number DESC
        ) AS mature_rank
    FROM ordered_episode
    WHERE published_at <= DATE_SUB(latest_published_at, INTERVAL 7 DAY)
),
view_scale AS (
    SELECT
        LEAST(
            100000,
            GREATEST(10, MAX(GREATEST(COALESCE(mature.view_count, 0), 0)))
        ) AS view_scale_max
    FROM mature_episode AS mature
    JOIN novel AS n ON n.novel_id = mature.novel_id
    WHERE mature.mature_rank = 1
      AND n.free = 1
      AND COALESCE(n.paid_serial, 0) = 0
),
score_input AS (
    SELECT
        summary.*,
        mature.view_count IS NOT NULL AS has_reference_view,
        GREATEST(COALESCE(mature.view_count, 0), 0) AS reference_view_count,
        scale.view_scale_max,
        CASE
            WHEN COALESCE(mature.view_count, 0) <= 10
              OR scale.view_scale_max <= 10 THEN 0
            ELSE LEAST(
                0.999999,
                GREATEST(
                    0,
                    LOG10(GREATEST(mature.view_count, 10) / 10)
                    / LOG10(scale.view_scale_max / 10)
                )
            )
        END AS view_position
    FROM retention_summary AS summary
    JOIN mature_episode AS mature
      ON mature.novel_id = summary.novel_id
     AND mature.mature_rank = 1
    CROSS JOIN view_scale AS scale
),
graded_score AS (
    SELECT
        score_input.*,
        CASE
            WHEN view_position < 0.2 THEN '아주 낮음'
            WHEN view_position < 0.4 THEN '낮음'
            WHEN view_position < 0.6 THEN '보통'
            WHEN view_position < 0.8 THEN '좋음'
            ELSE '대박'
        END AS view_grade,
        CASE
            WHEN view_position < 0.2 THEN 0
            WHEN view_position < 0.4 THEN 20
            WHEN view_position < 0.6 THEN 40
            WHEN view_position < 0.8 THEN 60
            ELSE 80
        END AS score_floor
    FROM score_input
)
SELECT
    novel_id,
    CASE WHEN has_reference_view THEN ROUND(score_floor, 2) END,
    ROUND(free_retention_score, 2),
    ROUND(paid_retention_score, 2),
    reference_view_count,
    view_scale_max,
    view_grade,
    scored_episode_count,
    ROUND(average_dropout_rate, 6),
    CURRENT_TIMESTAMP
FROM graded_score;

TRUNCATE TABLE novel_comment_sentiment;

INSERT INTO novel_comment_sentiment (
    novel_id, positive_count, negative_count, neutral_count,
    total_count, calculated_at
)
SELECT
    novel_id,
    SUM(sentiment = 'POSITIVE'),
    SUM(sentiment = 'NEGATIVE'),
    SUM(sentiment = 'NEUTRAL'),
    COUNT(*),
    CURRENT_TIMESTAMP
FROM (
    SELECT
        novel_id,
        CASE
            WHEN comment_text LIKE '%재미%'
              OR comment_text LIKE '%재밌%'
              OR comment_text LIKE '%좋다%'
              OR comment_text LIKE '%좋네%'
              OR comment_text LIKE '%좋아%'
              OR comment_text LIKE '%최고%'
              OR comment_text LIKE '%추천%'
              OR comment_text LIKE '%기대%'
              OR comment_text LIKE '%감동%'
              OR comment_text LIKE '%대박%'
              OR comment_text LIKE '%응원%'
              OR comment_text LIKE '%사랑%'
              OR comment_text LIKE '%흥미%'
                THEN 'POSITIVE'
            WHEN comment_text LIKE '%별로%'
              OR comment_text LIKE '%실망%'
              OR comment_text LIKE '%최악%'
              OR comment_text LIKE '%노잼%'
              OR comment_text LIKE '%하차%'
              OR comment_text LIKE '%지루%'
              OR comment_text LIKE '%답답%'
              OR comment_text LIKE '%싫다%'
              OR comment_text LIKE '%싫어%'
              OR comment_text LIKE '%망작%'
              OR comment_text LIKE '%욕설%'
              OR comment_text LIKE '%오류%'
                THEN 'NEGATIVE'
            ELSE 'NEUTRAL'
        END AS sentiment
    FROM comment
    WHERE novel_id IS NOT NULL
      AND comment_text IS NOT NULL
      AND comment_text <> ''
) AS classified_comment
GROUP BY novel_id;
