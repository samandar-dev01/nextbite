from database import get_connection


def get_top_companies(limit=10):
    connection = get_connection()

    try:
        result = connection.execute("""
            WITH company_activity AS (
                SELECT
                    "ИНН продавца" AS inn,
                    COUNT(*) AS seller_deals,
                    0 AS buyer_deals
                FROM deals
                GROUP BY "ИНН продавца"

                UNION ALL

                SELECT
                    "ИНН покупателя" AS inn,
                    0 AS seller_deals,
                    COUNT(*) AS buyer_deals
                FROM deals
                GROUP BY "ИНН покупателя"
            ),

            company_totals AS (
                SELECT
                    inn,
                    SUM(seller_deals) AS seller_deals,
                    SUM(buyer_deals) AS buyer_deals,
                    SUM(seller_deals + buyer_deals) AS total_deals
                FROM company_activity
                GROUP BY inn
            ),

            participant_names AS (
                SELECT
                    "ИНН" AS inn,
                    MAX("Наименование") AS company_name
                FROM participants
                GROUP BY "ИНН"
            )

            SELECT
                CAST(c.inn AS VARCHAR) AS inn,
                COALESCE(p.company_name, 'Noma’lum') AS company_name,
                c.seller_deals,
                c.buyer_deals,
                c.total_deals
            FROM company_totals c
            LEFT JOIN participant_names p
                ON CAST(c.inn AS VARCHAR) = CAST(p.inn AS VARCHAR)
            ORDER BY c.total_deals DESC
            LIMIT ?
        """, [limit]).fetchall()

        return [
            {
                "inn": row[0],
                "company_name": row[1],
                "seller_deals": row[2],
                "buyer_deals": row[3],
                "total_deals": row[4]
            }
            for row in result
        ]

    finally:
        connection.close()


def get_company_details(inn):
    connection = get_connection()

    try:
        result = connection.execute("""
            WITH company_activity AS (
                SELECT
                    COUNT(*) AS seller_deals,
                    0 AS buyer_deals
                FROM deals
                WHERE CAST("ИНН продавца" AS VARCHAR) = ?

                UNION ALL

                SELECT
                    0 AS seller_deals,
                    COUNT(*) AS buyer_deals
                FROM deals
                WHERE CAST("ИНН покупателя" AS VARCHAR) = ?
            )

            SELECT
                SUM(seller_deals),
                SUM(buyer_deals),
                SUM(seller_deals + buyer_deals)
            FROM company_activity
        """, [str(inn), str(inn)]).fetchone()

        participant = connection.execute("""
            SELECT
                "Наименование",
                "Регион",
                "Вид деятельности",
                "Роль"
            FROM participants
            WHERE CAST("ИНН" AS VARCHAR) = ?
            LIMIT 1
        """, [str(inn)]).fetchone()

        if participant is None:
            return None

        return {
            "inn": str(inn),
            "company_name": participant[0],
            "region": participant[1],
            "activity": participant[2],
            "role": participant[3],
            "seller_deals": result[0] or 0,
            "buyer_deals": result[1] or 0,
            "total_deals": result[2] or 0
        }

    finally:
        connection.close()


def get_top_brokers(limit=10):
    connection = get_connection()

    try:
        result = connection.execute("""
            WITH broker_activity AS (
                SELECT
                    "Брокер продавца" AS broker_code,
                    COUNT(*) AS deals_count
                FROM deals
                WHERE "Брокер продавца" IS NOT NULL
                GROUP BY "Брокер продавца"

                UNION ALL

                SELECT
                    "Брокер покупателя" AS broker_code,
                    COUNT(*) AS deals_count
                FROM deals
                WHERE "Брокер покупателя" IS NOT NULL
                GROUP BY "Брокер покупателя"
            ),

            broker_totals AS (
                SELECT
                    broker_code,
                    SUM(deals_count) AS total_deals
                FROM broker_activity
                GROUP BY broker_code
            )

            SELECT
                CAST(b."Код брокера" AS VARCHAR),
                b."Наименование",
                t.total_deals
            FROM broker_totals t
            LEFT JOIN brokers b
                ON CAST(t.broker_code AS VARCHAR) =
                   CAST(b."Код брокера" AS VARCHAR)
            ORDER BY t.total_deals DESC
            LIMIT ?
        """, [limit]).fetchall()

        return [
            {
                "broker_code": row[0],
                "broker_name": row[1],
                "total_deals": row[2]
            }
            for row in result
        ]

    finally:
        connection.close()


def get_top_products(limit=10):
    connection = get_connection()

    try:
        result = connection.execute("""
            SELECT
                "Наименование товара" AS product_name,
                COUNT(*) AS total_deals
            FROM deals
            WHERE "Наименование товара" IS NOT NULL
            GROUP BY "Наименование товара"
            ORDER BY total_deals DESC
            LIMIT ?
        """, [limit]).fetchall()

        return [
            {
                "product_name": row[0],
                "total_deals": row[1]
            }
            for row in result
        ]

    finally:
        connection.close()