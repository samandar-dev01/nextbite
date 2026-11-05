from database import get_connection


def get_total_statistics():
    connection = get_connection()

    try:
        result = connection.execute("""
            SELECT
                COUNT(*) AS total_deals,
                COUNT(DISTINCT "ИНН продавца") AS unique_sellers,
                COUNT(DISTINCT "ИНН покупателя") AS unique_buyers
            FROM deals
        """).fetchone()

        return {
            "total_deals": result[0],
            "unique_sellers": result[1],
            "unique_buyers": result[2]
        }

    finally:
        connection.close()


def get_yearly_statistics():
    connection = get_connection()

    try:
        result = connection.execute("""
            SELECT
                EXTRACT(YEAR FROM
                    COALESCE(
                        TRY_CAST(CAST("Дата сделки" AS VARCHAR) AS DATE),
                        CAST(
                            TRY_STRPTIME(
                                CAST("Дата сделки" AS VARCHAR),
                                '%d.%m.%Y'
                            ) AS DATE
                        )
                    )
                ) AS year,
                COUNT(*) AS total_deals
            FROM deals
            GROUP BY year
            ORDER BY year
        """).fetchall()

        return [
            {
                "year": int(row[0]),
                "total_deals": row[1]
            }
            for row in result
        ]

    finally:
        connection.close()


def get_status_statistics():
    connection = get_connection()

    try:
        result = connection.execute("""
            SELECT
                "Состояние сделки",
                COUNT(*) AS total
            FROM deals
            GROUP BY "Состояние сделки"
            ORDER BY total DESC
        """).fetchall()

        return [
            {
                "status": row[0],
                "total": row[1]
            }
            for row in result
        ]

    finally:
        connection.close()