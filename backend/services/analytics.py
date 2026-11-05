"""
Universal tahlil moduli.

AI agent va dashboard shu modul orqali `v_deals` jadvalidan (database.py
yaratadi) istalgan kesimdagi statistikani oladi: yil, oy, hudud, mahsulot,
kompaniya, broker, savdo turi va hokazo bo'yicha - bitimlar soni, summa
(UZS/USD), o'rtacha, hajm ko'rsatkichlari bilan.

Barcha qiymatlar parametrlashtirilgan (?), ustun nomlari esa faqat oq
ro'yxatdan (whitelist) olinadi, shuning uchun SQL injection xavfi yo'q.
"""
import re

from database import get_connection

# Guruhlash mumkin bo'lgan ustunlar
GROUP_COLUMNS = {
    "year", "month", "quarter", "region", "product", "category", "industry",
    "trade_type", "contract_type", "contract_form", "status", "unit",
    "seller_name", "buyer_name", "seller_broker_name", "buyer_broker_name",
    "seller_inn", "buyer_inn",
}

# Ko'rsatkichlar (metric -> SQL ifoda)
METRICS = {
    "deals_count": "COUNT(*)",
    "total_amount_uzs": "ROUND(SUM(amount_uzs), 0)",
    "total_amount_usd": "ROUND(SUM(amount_usd), 0)",
    "avg_amount_usd": "ROUND(AVG(amount_usd), 0)",
    "max_amount_usd": "ROUND(MAX(amount_usd), 0)",
    "total_quantity": "ROUND(SUM(quantity), 2)",
    "unique_sellers": "COUNT(DISTINCT seller_inn)",
    "unique_buyers": "COUNT(DISTINCT buyer_inn)",
    "unique_products": "COUNT(DISTINCT product)",
}

STATUS_FILTERS = {
    "all": None,
    "executed": "is_executed",
    "cancelled": "is_cancelled",
    "not_cancelled": "NOT is_cancelled",
}

MAX_ROWS = 200


def _build_where(filters):
    """filters lug'atidan WHERE sharti va parametrlar ro'yxatini quradi."""
    filters = filters or {}
    clauses, params, applied = [], [], {}

    def eq(column, key, cast=None):
        value = filters.get(key)
        if value is None or value == "":
            return
        clauses.append(f"{column} = ?")
        params.append(cast(value) if cast else value)
        applied[key] = value

    def like(column, key):
        value = filters.get(key)
        if not value:
            return
        clauses.append(f"{column} ILIKE ?")
        params.append(f"%{str(value).strip()}%")
        applied[key] = value

    eq("year", "year", int)
    eq("month", "month", int)
    eq("quarter", "quarter", int)
    eq("seller_inn", "seller_inn", int)
    eq("buyer_inn", "buyer_inn", int)
    like("region", "region")
    # Mahsulot: defis va probel farqini hisobga olmaymiz ("Хлопок-сырец" = "Хлопок сырец")
    product = filters.get("product")
    if product:
        clauses.append("replace(product, '-', ' ') ILIKE ?")
        params.append("%" + str(product).strip().replace("-", " ") + "%")
        applied["product"] = product
    like("category", "category")
    like("industry", "industry")
    like("trade_type", "trade_type")
    like("contract_type", "contract_type")
    like("contract_form", "contract_form")
    like("status", "status")
    like("seller_name", "seller_name")
    like("buyer_name", "buyer_name")

    broker = filters.get("broker")
    if broker:
        clauses.append(
            "(seller_broker_name ILIKE ? OR buyer_broker_name ILIKE ?"
            " OR seller_broker_code = ? OR buyer_broker_code = ?)"
        )
        like_value = f"%{str(broker).strip()}%"
        params += [like_value, like_value, str(broker).strip(), str(broker).strip()]
        applied["broker"] = broker

    company = filters.get("company")
    if company:
        clauses.append("(seller_name ILIKE ? OR buyer_name ILIKE ?)")
        params += [f"%{str(company).strip()}%"] * 2
        applied["company"] = company

    for key, op in (("date_from", ">="), ("date_to", "<=")):
        value = filters.get(key)
        if value:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(value)):
                raise ValueError(f"{key} 'YYYY-MM-DD' formatida bo'lishi kerak")
            clauses.append(f"deal_date {op} CAST(? AS DATE)")
            params.append(str(value))
            applied[key] = value

    status_filter = filters.get("status_filter", "all")
    if status_filter not in STATUS_FILTERS:
        raise ValueError(f"status_filter noto'g'ri: {status_filter}")
    if STATUS_FILTERS[status_filter]:
        clauses.append(STATUS_FILTERS[status_filter])
        applied["status_filter"] = status_filter

    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    return where, params, applied


def analyze_deals(
    group_by=None,
    metrics=None,
    filters=None,
    order_by=None,
    descending=True,
    limit=10,
):
    """
    Bitimlarni ixtiyoriy kesimda tahlil qiladi.

    group_by  - ustun nomi yoki ustunlar ro'yxati (GROUP_COLUMNS ichidan)
    metrics   - ko'rsatkichlar ro'yxati (METRICS ichidan)
    filters   - filtr lug'ati (year, region, product, company, ...)
    order_by  - tartiblash ko'rsatkichi yoki guruh ustuni
    """
    if isinstance(group_by, str):
        group_by = [group_by]
    group_by = list(group_by or [])
    for column in group_by:
        if column not in GROUP_COLUMNS:
            raise ValueError(
                f"group_by noto'g'ri: {column}. Mumkin: {sorted(GROUP_COLUMNS)}"
            )

    metrics = list(metrics or ["deals_count", "total_amount_usd"])
    for metric in metrics:
        if metric not in METRICS:
            raise ValueError(
                f"metric noto'g'ri: {metric}. Mumkin: {sorted(METRICS)}"
            )

    limit = max(1, min(int(limit or 10), MAX_ROWS))
    where, params, applied = _build_where(filters)

    select_parts = group_by + [f"{METRICS[m]} AS {m}" for m in metrics]
    sql = f"SELECT {', '.join(select_parts)} FROM v_deals{where}"
    if group_by:
        sql += " GROUP BY " + ", ".join(group_by)

    order_column = order_by or (metrics[0] if group_by else None)
    if order_column:
        if order_column not in metrics and order_column not in group_by:
            raise ValueError(f"order_by noto'g'ri: {order_column}")
        direction = "DESC" if descending else "ASC"
        sql += f" ORDER BY {order_column} {direction} NULLS LAST"
    sql += f" LIMIT {limit}"

    connection = get_connection()
    try:
        cursor = connection.execute(sql, params)
        columns = [d[0] for d in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        connection.close()

    return {
        "filters_applied": applied,
        "group_by": group_by,
        "row_count": len(rows),
        "rows": rows,
    }


def compare_periods(period_a, period_b, group_by=None, filters=None, limit=10):
    """
    Ikki davrni solishtiradi. period_a/period_b: {"year": 2025} yoki
    {"date_from": "2025-01-01", "date_to": "2025-06-30"} kabi lug'at.
    """
    result = {}
    for name, period in (("period_a", period_a), ("period_b", period_b)):
        merged = {**(filters or {}), **(period or {})}
        result[name] = analyze_deals(
            group_by=group_by,
            metrics=["deals_count", "total_amount_usd", "total_amount_uzs"],
            filters=merged,
            limit=limit,
        )

    def totals(period):
        merged = {**(filters or {}), **(period or {})}
        data = analyze_deals(
            metrics=["deals_count", "total_amount_usd", "total_amount_uzs"],
            filters=merged,
        )
        return data["rows"][0] if data["rows"] else {}

    total_a, total_b = totals(period_a), totals(period_b)
    change = {}
    for key in ("deals_count", "total_amount_usd", "total_amount_uzs"):
        a, b = total_a.get(key) or 0, total_b.get(key) or 0
        change[key + "_change_pct"] = (
            round((b - a) / a * 100, 2) if a else None
        )

    return {
        "period_a_total": total_a,
        "period_b_total": total_b,
        "change_b_vs_a": change,
        "period_a_breakdown": result["period_a"]["rows"],
        "period_b_breakdown": result["period_b"]["rows"],
    }


FORBIDDEN_SQL = re.compile(
    r"\b(insert|update|delete|drop|alter|create|attach|detach|copy|export|"
    r"import|install|load|pragma|call|set|read_csv|read_parquet|read_json|"
    r"glob|truncate|replace)\b",
    re.IGNORECASE,
)


def run_readonly_sql(sql, limit=50):
    """
    Murakkab savollar uchun: faqat SELECT/WITH so'rovlari, faqat `v_deals`
    (va yordamchi jadvallar) ustida. Baza read-only rejimida ochiladi.
    """
    sql = (sql or "").strip().rstrip(";")
    if not re.match(r"^(select|with)\b", sql, re.IGNORECASE):
        raise ValueError("Faqat SELECT yoki WITH so'rovlariga ruxsat beriladi.")
    if ";" in sql or "--" in sql or "/*" in sql:
        raise ValueError("Bitta oddiy so'rov bo'lishi kerak (izoh va ';' mumkin emas).")
    if FORBIDDEN_SQL.search(sql):
        raise ValueError("So'rovda taqiqlangan kalit so'z bor.")

    limit = max(1, min(int(limit or 50), MAX_ROWS))
    connection = get_connection()
    try:
        cursor = connection.execute(f"SELECT * FROM ({sql}) AS q LIMIT {limit}")
        columns = [d[0] for d in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        connection.close()

    return {"row_count": len(rows), "rows": rows}


def dataset_overview():
    """Ma'lumotlar to'plami haqida umumiy tavsif (davr, hajm, qiymatlar)."""
    connection = get_connection()
    try:
        total = connection.execute("""
            SELECT COUNT(*), MIN(deal_date), MAX(deal_date),
                   ROUND(SUM(amount_uzs), 0), ROUND(SUM(amount_usd), 0),
                   COUNT(DISTINCT seller_inn), COUNT(DISTINCT buyer_inn),
                   COUNT(DISTINCT product), COUNT(DISTINCT region)
            FROM v_deals
        """).fetchone()
        executed = connection.execute("""
            SELECT COUNT(*), ROUND(SUM(amount_uzs), 0), ROUND(SUM(amount_usd), 0)
            FROM v_deals WHERE is_executed
        """).fetchone()

        def distinct(column):
            return [r[0] for r in connection.execute(
                f"SELECT DISTINCT {column} FROM v_deals "
                f"WHERE {column} IS NOT NULL ORDER BY 1"
            ).fetchall()]

        return {
            "total_deals": total[0],
            "date_from": str(total[1]),
            "date_to": str(total[2]),
            "total_amount_uzs": total[3],
            "total_amount_usd": total[4],
            "unique_sellers": total[5],
            "unique_buyers": total[6],
            "unique_products": total[7],
            "unique_regions": total[8],
            "executed_deals": executed[0],
            "executed_amount_uzs": executed[1],
            "executed_amount_usd": executed[2],
            "regions": distinct("region"),
            "statuses": distinct("status"),
            "trade_types": distinct("trade_type"),
            "contract_types": distinct("contract_type"),
            "categories": distinct("category"),
        }
    finally:
        connection.close()


def search_entities(kind, query, limit=10):
    """Kompaniya, mahsulot yoki brokerni nomi bo'yicha qidiradi."""
    limit = max(1, min(int(limit or 10), 30))
    pattern = f"%{str(query).strip()}%"
    connection = get_connection()
    try:
        if kind == "company":
            sql = """
                SELECT inn, name, deals, amount_usd FROM (
                    SELECT seller_inn AS inn, seller_name AS name,
                           COUNT(*) AS deals, ROUND(SUM(amount_usd), 0) AS amount_usd
                    FROM v_deals WHERE seller_name ILIKE ? GROUP BY 1, 2
                    UNION ALL
                    SELECT buyer_inn, buyer_name, COUNT(*), ROUND(SUM(amount_usd), 0)
                    FROM v_deals WHERE buyer_name ILIKE ? GROUP BY 1, 2
                ) ORDER BY deals DESC LIMIT ?
            """
            params = [pattern, pattern, limit]
            keys = ["inn", "company_name", "deals", "amount_usd"]
        elif kind == "product":
            sql = """
                SELECT product, COUNT(*), ROUND(SUM(amount_usd), 0)
                FROM v_deals WHERE product ILIKE ?
                GROUP BY 1 ORDER BY 2 DESC LIMIT ?
            """
            params = [pattern, limit]
            keys = ["product", "deals", "amount_usd"]
        elif kind == "broker":
            sql = """
                SELECT "Код брокера", "Наименование", "Регион"
                FROM brokers WHERE "Наименование" ILIKE ? OR "Код брокера" ILIKE ?
                LIMIT ?
            """
            params = [pattern, pattern, limit]
            keys = ["broker_code", "broker_name", "region"]
        else:
            raise ValueError("kind: company, product yoki broker bo'lishi kerak")

        rows = connection.execute(sql, params).fetchall()
        return {"matches": [dict(zip(keys, r)) for r in rows]}
    finally:
        connection.close()


def monthly_trend(filters=None):
    """Oyma-oy dinamika (bitimlar soni va USD summasi)."""
    data = analyze_deals(
        group_by=["year", "month"],
        metrics=["deals_count", "total_amount_usd"],
        filters=filters,
        order_by="year",
        descending=False,
        limit=MAX_ROWS,
    )
    data["rows"].sort(key=lambda r: (r["year"], r["month"]))
    return data["rows"]
