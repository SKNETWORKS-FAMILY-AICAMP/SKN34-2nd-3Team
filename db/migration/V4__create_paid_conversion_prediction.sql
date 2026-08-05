SET NAMES utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS novel_paid_conversion_prediction (
    novel_id INT NOT NULL,
    predicted_purchase_count INT NOT NULL,
    predicted_conversion_rate DECIMAL(8, 6) NOT NULL,
    predicted_paid_dropout_rate DECIMAL(8, 6) NOT NULL,
    model_mae DECIMAL(8, 6) NOT NULL,
    training_sample_count INT NOT NULL,
    trained_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (novel_id),
    CONSTRAINT fk_paid_prediction_novel
        FOREIGN KEY (novel_id) REFERENCES novel (novel_id)
) ENGINE=InnoDB
  DEFAULT CHARACTER SET=utf8mb4
  COLLATE=utf8mb4_0900_ai_ci;
