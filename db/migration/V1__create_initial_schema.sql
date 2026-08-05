CREATE TABLE tag (
    tag_id INT NOT NULL,
    tag_name VARCHAR(255),
    PRIMARY KEY (tag_id)
) ENGINE = InnoDB
  DEFAULT CHARACTER SET = utf8mb4
  COLLATE = utf8mb4_0900_ai_ci;

CREATE TABLE novel_genre (
    genre_id INT NOT NULL,
    genre_name VARCHAR(255),
    PRIMARY KEY (genre_id)
) ENGINE = InnoDB
  DEFAULT CHARACTER SET = utf8mb4
  COLLATE = utf8mb4_0900_ai_ci;

CREATE TABLE novel_author (
    author_id INT NOT NULL,
    author_name VARCHAR(255),
    author_url VARCHAR(2048),
    is_illustrator BOOLEAN,
    PRIMARY KEY (author_id)
) ENGINE = InnoDB
  DEFAULT CHARACTER SET = utf8mb4
  COLLATE = utf8mb4_0900_ai_ci;

CREATE TABLE novel_group (
    novel_group_id INT NOT NULL,
    group_name VARCHAR(255),
    PRIMARY KEY (novel_group_id)
) ENGINE = InnoDB
  DEFAULT CHARACTER SET = utf8mb4
  COLLATE = utf8mb4_0900_ai_ci;

CREATE TABLE novel (
    novel_id INT NOT NULL,
    source_url VARCHAR(2048),
    title VARCHAR(255),
    introduction TEXT,
    author_id INT,
    illustrator_id INT,
    origin_cover_url VARCHAR(2048),
    group_id INT,
    free BOOLEAN,
    paid_serial BOOLEAN,
    exclusive BOOLEAN,
    pre_exclusive BOOLEAN,
    adult BOOLEAN,
    contest BOOLEAN,
    rental BOOLEAN,
    pause BOOLEAN,
    finish BOOLEAN,
    epub BOOLEAN,
    ebook BOOLEAN,
    cp_novel BOOLEAN,
    created_at DATETIME,
    updated_at DATETIME,
    paid_conversion_open_at DATETIME,
    isbn VARCHAR(255),
    period VARCHAR(255),
    unit_type VARCHAR(255),
    collected_at DATETIME,
    genre_1 INT,
    genre_2 INT,
    PRIMARY KEY (novel_id),
    CONSTRAINT fk_novel_author
        FOREIGN KEY (author_id) REFERENCES novel_author (author_id),
    CONSTRAINT fk_novel_illustrator
        FOREIGN KEY (illustrator_id) REFERENCES novel_author (author_id),
    CONSTRAINT fk_novel_group
        FOREIGN KEY (group_id) REFERENCES novel_group (novel_group_id),
    CONSTRAINT fk_novel_genre_1
        FOREIGN KEY (genre_1) REFERENCES novel_genre (genre_id),
    CONSTRAINT fk_novel_genre_2
        FOREIGN KEY (genre_2) REFERENCES novel_genre (genre_id)
) ENGINE = InnoDB
  DEFAULT CHARACTER SET = utf8mb4
  COLLATE = utf8mb4_0900_ai_ci;

CREATE TABLE novel_tag (
    novel_id INT NOT NULL,
    tag_id INT NOT NULL,
    PRIMARY KEY (novel_id, tag_id),
    CONSTRAINT fk_novel_tag_novel
        FOREIGN KEY (novel_id) REFERENCES novel (novel_id),
    CONSTRAINT fk_novel_tag_tag
        FOREIGN KEY (tag_id) REFERENCES tag (tag_id)
) ENGINE = InnoDB
  DEFAULT CHARACTER SET = utf8mb4
  COLLATE = utf8mb4_0900_ai_ci;

CREATE TABLE episode (
    episode_id INT NOT NULL,
    novel_id INT,
    episode_number INT,
    episode_title VARCHAR(255),
    published_at DATETIME,
    access_type VARCHAR(255),
    view_count INT,
    like_count INT,
    comment_count INT,
    page_count INT,
    adult BOOLEAN,
    paid_conversion_before_entry BOOLEAN,
    `up` BOOLEAN,
    collected_at DATETIME,
    PRIMARY KEY (episode_id),
    INDEX idx_episode_novel_number (novel_id, episode_number),
    CONSTRAINT fk_episode_novel
        FOREIGN KEY (novel_id) REFERENCES novel (novel_id)
) ENGINE = InnoDB
  DEFAULT CHARACTER SET = utf8mb4
  COLLATE = utf8mb4_0900_ai_ci;

CREATE TABLE novel_statistics (
    novel_id INT NOT NULL,
    view_count INT,
    preference_count INT,
    like_count INT,
    chapter_count INT,
    free_chapter_count INT,
    characters INT,
    male_count INT,
    female_count INT,
    age_10s_percent FLOAT,
    age_20s_percent FLOAT,
    age_30s_percent FLOAT,
    age_40s_percent FLOAT,
    age_50s_percent FLOAT,
    source_notice_count INT,
    collected_at DATETIME,
    PRIMARY KEY (novel_id),
    CONSTRAINT fk_novel_statistics_novel
        FOREIGN KEY (novel_id) REFERENCES novel (novel_id)
) ENGINE = InnoDB
  DEFAULT CHARACTER SET = utf8mb4
  COLLATE = utf8mb4_0900_ai_ci;

CREATE TABLE novel_ai_evaluation (
    evaluation_id INT NOT NULL,
    novel_id INT,
    evaluation_type VARCHAR(255),
    evaluation_level INT,
    evaluation_score FLOAT,
    confidence FLOAT,
    model_version VARCHAR(255),
    analyzed_at DATETIME,
    PRIMARY KEY (evaluation_id),
    CONSTRAINT fk_novel_ai_evaluation_novel
        FOREIGN KEY (novel_id) REFERENCES novel (novel_id)
) ENGINE = InnoDB
  DEFAULT CHARACTER SET = utf8mb4
  COLLATE = utf8mb4_0900_ai_ci;

CREATE TABLE comment (
    comment_id INT NOT NULL,
    novel_id INT,
    episode_id INT,
    parent_comment_id INT,
    reply_level INT,
    content_type VARCHAR(255),
    comment_text TEXT,
    like_count INT,
    dislike_count INT,
    created_at DATETIME,
    secret BOOLEAN,
    report_status VARCHAR(255),
    block_status BOOLEAN,
    collected_at DATETIME(6),
    commenter_nickname VARCHAR(100) NOT NULL,
    commenter_blog_url VARCHAR(512),
    is_novel_author BOOLEAN NOT NULL DEFAULT FALSE,
    source_parent_comment_id INT,
    crawl_status VARCHAR(32) NOT NULL,
    PRIMARY KEY (comment_id),
    INDEX idx_comment_source_parent (source_parent_comment_id),
    CONSTRAINT fk_comment_novel
        FOREIGN KEY (novel_id) REFERENCES novel (novel_id),
    CONSTRAINT fk_comment_episode
        FOREIGN KEY (episode_id) REFERENCES episode (episode_id),
    CONSTRAINT fk_comment_parent
        FOREIGN KEY (parent_comment_id) REFERENCES comment (comment_id)
) ENGINE = InnoDB
  DEFAULT CHARACTER SET = utf8mb4
  COLLATE = utf8mb4_0900_ai_ci;
