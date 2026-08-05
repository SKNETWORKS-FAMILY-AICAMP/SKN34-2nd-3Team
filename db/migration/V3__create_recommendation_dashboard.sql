-- Materialized recommendation metrics based on test.ipynb.
-- Episodes 1-5 and access-type transition edges are excluded. Within FREE and
-- PAID segments, a smaller view decline receives a higher percentile score.

SET NAMES utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS novel_recommendation_score (
    novel_id INT NOT NULL,
    recommendation_score DECIMAL(6, 2) NOT NULL,
    free_score DECIMAL(6, 2),
    paid_score DECIMAL(6, 2),
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

TRUNCATE TABLE novel_recommendation_score;

INSERT INTO novel_recommendation_score (
    novel_id, recommendation_score, free_score, paid_score,
    scored_episode_count, average_dropout_rate, calculated_at
)
WITH ordered_episode AS (
    SELECT
        novel_id, episode_number, access_type, view_count,
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
    WHERE episode_number > 5
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
)
SELECT
    novel_id,
    ROUND(AVG(episode_score), 2),
    ROUND(AVG(CASE WHEN access_type = 'FREE' THEN episode_score END), 2),
    ROUND(AVG(CASE WHEN access_type = 'PAID' THEN episode_score END), 2),
    COUNT(*),
    ROUND(AVG(dropout_rate), 6),
    CURRENT_TIMESTAMP
FROM percentile_score
GROUP BY novel_id;

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
