from __future__ import annotations

from pathlib import Path

import mysql.connector
from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    config = dotenv_values(ROOT / ".env")
    connection = mysql.connector.connect(
        host=config.get("DB_HOST", "127.0.0.1"),
        port=int(config.get("MYSQL_PORT", "3306")),
        user=config.get("DB_USER", "root"),
        password=config.get("DB_PASSWORD", ""),
        database=config.get("DB_NAME"),
        connection_timeout=15,
        autocommit=True,
    )
    sql = (ROOT / "db" / "migration" / "V3__create_recommendation_dashboard.sql").read_text(
        encoding="utf-8"
    )
    cursor = connection.cursor()
    try:
        for statement in (part.strip() for part in sql.split(";")):
            if statement:
                cursor.execute(statement)
        print("Recommendation metrics refreshed")
    finally:
        cursor.close()
        connection.close()


if __name__ == "__main__":
    main()
