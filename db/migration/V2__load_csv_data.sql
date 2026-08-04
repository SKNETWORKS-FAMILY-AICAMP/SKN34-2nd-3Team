SET NAMES utf8mb4;

LOAD DATA INFILE '/var/lib/mysql-files/tag.csv'
INTO TABLE tag
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"' ESCAPED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(@tag_id, @tag_name, @first_seen_novel_id, @source_collected_at)
SET tag_id = NULLIF(@tag_id, ''),
    tag_name = NULLIF(@tag_name, '');

LOAD DATA INFILE '/var/lib/mysql-files/novel_genre.csv'
INTO TABLE novel_genre
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"' ESCAPED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(@genre_id, @genre_name, @genre_best_code, @genre_best_name,
 @first_seen_novel_id, @source_collected_at)
SET genre_id = NULLIF(@genre_id, ''),
    genre_name = NULLIF(@genre_name, '');

LOAD DATA INFILE '/var/lib/mysql-files/novel_author.csv'
INTO TABLE novel_author
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"' ESCAPED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(@author_id, @author_name, @author_url, @is_illustrator)
SET author_id = NULLIF(@author_id, ''),
    author_name = NULLIF(@author_name, ''),
    author_url = NULLIF(@author_url, ''),
    is_illustrator = CASE LOWER(TRIM(@is_illustrator))
        WHEN 'true' THEN 1 WHEN 'false' THEN 0 ELSE NULL END;

LOAD DATA INFILE '/var/lib/mysql-files/novel_group.csv'
INTO TABLE novel_group
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"' ESCAPED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(@novel_group_id, @group_name, @first_seen_novel_id, @source_collected_at)
SET novel_group_id = NULLIF(@novel_group_id, ''),
    group_name = NULLIF(@group_name, '');

LOAD DATA INFILE '/var/lib/mysql-files/novel.csv'
INTO TABLE novel
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"' ESCAPED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(@novel_id, @source_url, @title, @introduction, @author_id, @illustrator_id,
 @origin_cover_url, @group_id, @free, @paid_serial, @exclusive, @pre_exclusive,
 @adult, @contest, @rental, @pause, @finish, @epub, @ebook, @cp_novel,
 @created_at, @updated_at, @paid_conversion_open_at, @isbn, @period, @unit_type,
 @collected_at, @genre_1, @genre_2, @author_name, @illustrator_name, @cover_url,
 @group_name, @genres_json, @tags_json, @genre_best_name, @genre_best_code,
 @notices_json, @events_json, @crawl_status, @source_http_status)
SET novel_id = NULLIF(@novel_id, ''),
    source_url = NULLIF(@source_url, ''),
    title = NULLIF(@title, ''),
    introduction = NULLIF(@introduction, ''),
    author_id = NULLIF(@author_id, ''),
    illustrator_id = NULLIF(@illustrator_id, ''),
    origin_cover_url = NULLIF(@origin_cover_url, ''),
    group_id = NULLIF(@group_id, ''),
    free = CASE LOWER(TRIM(@free)) WHEN 'true' THEN 1 WHEN 'false' THEN 0 ELSE NULL END,
    paid_serial = CASE LOWER(TRIM(@paid_serial)) WHEN 'true' THEN 1 WHEN 'false' THEN 0 ELSE NULL END,
    exclusive = CASE LOWER(TRIM(@exclusive)) WHEN 'true' THEN 1 WHEN 'false' THEN 0 ELSE NULL END,
    pre_exclusive = CASE LOWER(TRIM(@pre_exclusive)) WHEN 'true' THEN 1 WHEN 'false' THEN 0 ELSE NULL END,
    adult = CASE LOWER(TRIM(@adult)) WHEN 'true' THEN 1 WHEN 'false' THEN 0 ELSE NULL END,
    contest = CASE LOWER(TRIM(@contest)) WHEN 'true' THEN 1 WHEN 'false' THEN 0 ELSE NULL END,
    rental = CASE LOWER(TRIM(@rental)) WHEN 'true' THEN 1 WHEN 'false' THEN 0 ELSE NULL END,
    pause = CASE LOWER(TRIM(@pause)) WHEN 'true' THEN 1 WHEN 'false' THEN 0 ELSE NULL END,
    finish = CASE LOWER(TRIM(@finish)) WHEN 'true' THEN 1 WHEN 'false' THEN 0 ELSE NULL END,
    epub = CASE LOWER(TRIM(@epub)) WHEN 'true' THEN 1 WHEN 'false' THEN 0 ELSE NULL END,
    ebook = CASE LOWER(TRIM(@ebook)) WHEN 'true' THEN 1 WHEN 'false' THEN 0 ELSE NULL END,
    cp_novel = CASE LOWER(TRIM(@cp_novel)) WHEN 'true' THEN 1 WHEN 'false' THEN 0 ELSE NULL END,
    created_at = STR_TO_DATE(NULLIF(SUBSTRING(@created_at, 1, 19), ''), '%Y-%m-%dT%H:%i:%s'),
    updated_at = STR_TO_DATE(NULLIF(SUBSTRING(@updated_at, 1, 19), ''), '%Y-%m-%dT%H:%i:%s'),
    paid_conversion_open_at = STR_TO_DATE(NULLIF(SUBSTRING(@paid_conversion_open_at, 1, 19), ''), '%Y-%m-%dT%H:%i:%s'),
    isbn = NULLIF(@isbn, ''),
    period = NULLIF(@period, ''),
    unit_type = NULLIF(@unit_type, ''),
    collected_at = STR_TO_DATE(NULLIF(SUBSTRING(@collected_at, 1, 19), ''), '%Y-%m-%dT%H:%i:%s'),
    genre_1 = NULLIF(@genre_1, ''),
    genre_2 = NULLIF(@genre_2, '');

LOAD DATA INFILE '/var/lib/mysql-files/novel_tag.csv'
INTO TABLE novel_tag
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"' ESCAPED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(@novel_id, @tag_id, @source_collected_at)
SET novel_id = NULLIF(@novel_id, ''),
    tag_id = NULLIF(@tag_id, '');

LOAD DATA INFILE '/var/lib/mysql-files/episode.csv'
INTO TABLE episode
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"' ESCAPED BY '\\'
LINES TERMINATED BY '\r\n'
IGNORE 1 LINES
(@episode_id, @novel_id, @episode_number, @episode_title, @published_at,
 @access_type, @view_count, @like_count, @comment_count, @page_count, @adult,
 @paid_conversion_before_entry, @up, @collected_at, @source_url, @crawl_status,
 @comment_crawl_status)
SET episode_id = NULLIF(@episode_id, ''),
    novel_id = NULLIF(@novel_id, ''),
    episode_number = NULLIF(@episode_number, ''),
    episode_title = NULLIF(@episode_title, ''),
    published_at = STR_TO_DATE(NULLIF(SUBSTRING(@published_at, 1, 19), ''), '%Y-%m-%dT%H:%i:%s'),
    access_type = NULLIF(@access_type, ''),
    view_count = NULLIF(@view_count, ''),
    like_count = NULLIF(@like_count, ''),
    comment_count = NULLIF(@comment_count, ''),
    page_count = NULLIF(@page_count, ''),
    adult = CASE LOWER(TRIM(@adult)) WHEN 'true' THEN 1 WHEN 'false' THEN 0 ELSE NULL END,
    paid_conversion_before_entry = CASE LOWER(TRIM(@paid_conversion_before_entry)) WHEN 'true' THEN 1 WHEN 'false' THEN 0 ELSE NULL END,
    `up` = CASE LOWER(TRIM(@up)) WHEN 'true' THEN 1 WHEN 'false' THEN 0 ELSE NULL END,
    collected_at = STR_TO_DATE(NULLIF(SUBSTRING(@collected_at, 1, 19), ''), '%Y-%m-%dT%H:%i:%s');

LOAD DATA INFILE '/var/lib/mysql-files/novel_statistics.csv'
INTO TABLE novel_statistics
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"' ESCAPED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(@novel_id, @view_count, @preference_count, @like_count, @chapter_count,
 @free_chapter_count, @characters, @male_count, @female_count, @age_10s_percent,
 @age_20s_percent, @age_30s_percent, @age_40s_percent, @age_50s_percent,
 @source_notice_count, @collected_at)
SET novel_id = NULLIF(@novel_id, ''),
    view_count = NULLIF(@view_count, ''),
    preference_count = NULLIF(@preference_count, ''),
    like_count = NULLIF(@like_count, ''),
    chapter_count = NULLIF(@chapter_count, ''),
    free_chapter_count = NULLIF(@free_chapter_count, ''),
    characters = NULLIF(@characters, ''),
    male_count = NULLIF(@male_count, ''),
    female_count = NULLIF(@female_count, ''),
    age_10s_percent = NULLIF(@age_10s_percent, ''),
    age_20s_percent = NULLIF(@age_20s_percent, ''),
    age_30s_percent = NULLIF(@age_30s_percent, ''),
    age_40s_percent = NULLIF(@age_40s_percent, ''),
    age_50s_percent = NULLIF(@age_50s_percent, ''),
    source_notice_count = NULLIF(@source_notice_count, ''),
    collected_at = STR_TO_DATE(NULLIF(SUBSTRING(@collected_at, 1, 19), ''), '%Y-%m-%dT%H:%i:%s');

LOAD DATA INFILE '/var/lib/mysql-files/novel_ai_evaluation.csv'
INTO TABLE novel_ai_evaluation
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"' ESCAPED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(@evaluation_id, @novel_id, @evaluation_type, @evaluation_level,
 @evaluation_score, @confidence, @model_version, @analyzed_at)
SET evaluation_id = NULLIF(@evaluation_id, ''),
    novel_id = NULLIF(@novel_id, ''),
    evaluation_type = NULLIF(@evaluation_type, ''),
    evaluation_level = NULLIF(@evaluation_level, ''),
    evaluation_score = NULLIF(@evaluation_score, ''),
    confidence = NULLIF(@confidence, ''),
    model_version = NULLIF(@model_version, ''),
    analyzed_at = STR_TO_DATE(NULLIF(SUBSTRING(@analyzed_at, 1, 19), ''), '%Y-%m-%dT%H:%i:%s');

SET FOREIGN_KEY_CHECKS = 0;
LOAD DATA INFILE '/var/lib/mysql-files/comment.csv'
INTO TABLE comment
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"' ESCAPED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(@comment_id, @novel_id, @episode_id, @parent_comment_id, @reply_level,
 @content_type, @comment_text, @like_count, @dislike_count, @created_at,
 @secret, @report_status, @block_status, @collected_at, @crawl_status)
SET comment_id = NULLIF(@comment_id, ''),
    novel_id = NULLIF(@novel_id, ''),
    episode_id = NULLIF(@episode_id, ''),
    parent_comment_id = NULLIF(@parent_comment_id, ''),
    reply_level = NULLIF(@reply_level, ''),
    content_type = NULLIF(@content_type, ''),
    comment_text = NULLIF(@comment_text, ''),
    like_count = NULLIF(@like_count, ''),
    dislike_count = NULLIF(@dislike_count, ''),
    created_at = STR_TO_DATE(NULLIF(SUBSTRING(@created_at, 1, 19), ''), '%Y-%m-%dT%H:%i:%s'),
    secret = CASE LOWER(TRIM(@secret)) WHEN 'true' THEN 1 WHEN 'false' THEN 0 ELSE NULL END,
    report_status = NULLIF(@report_status, ''),
    block_status = CASE LOWER(TRIM(@block_status)) WHEN 'true' THEN 1 WHEN 'false' THEN 0 ELSE NULL END,
    collected_at = STR_TO_DATE(NULLIF(SUBSTRING(@collected_at, 1, 19), ''), '%Y-%m-%dT%H:%i:%s');
SET FOREIGN_KEY_CHECKS = 1;

-- Keep comments whose parent was not included in the source extract, but remove
-- the invalid self-reference so every stored foreign-key value is resolvable.
UPDATE comment AS child
LEFT JOIN comment AS parent
    ON parent.comment_id = child.parent_comment_id
SET child.parent_comment_id = NULL
WHERE child.parent_comment_id IS NOT NULL
  AND parent.comment_id IS NULL;
