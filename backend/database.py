from pathlib import Path
import duckdb

# Loyihaning asosiy papkasi
BASE_DIR = Path(__file__).resolve().parent

# CSV fayllar joylashgan papka
DATA_DIR = BASE_DIR / "data"

# DuckDB ma'lumotlar bazasi fayli
DB_PATH = BASE_DIR / "birja.duckdb"


def build_analytics_table(connection):
    """
    Tahlil uchun tayyor `v_deals` jadvalini yaratadi:
    - ruscha ustun nomlari -> inglizcha
    - "304 547 938.4" kabi matnli summalar -> son (UZS)
    - USD kursi bo'yicha dollar summasi
    - kompaniya, broker nomlari va mahsulot toifalari qo'shiladi
    """
    connection.execute("DROP TABLE IF EXISTS v_deals")
    connection.execute("""
        CREATE TABLE v_deals AS
        WITH p AS (
            SELECT "ИНН" AS inn,
                   MAX("Наименование") AS name,
                   MAX("Вид деятельности") AS activity
            FROM participants GROUP BY "ИНН"
        ),
        c AS (
            SELECT "Номер контракта" AS contract_id,
                   MAX("Наименование продукта") AS product_group,
                   MAX("Категория товара") AS category,
                   MAX("Отрасль промышленности") AS industry
            FROM contracts GROUP BY "Номер контракта"
        ),
        base AS (
            SELECT
                d."Номер сделки" AS deal_id,
                d."Дата сделки" AS deal_date,
                d."Время сделки" AS deal_time,
                d."Тип торгов" AS trade_type,
                d."Количество" AS quantity,
                TRY_CAST(regexp_replace(CAST(d."Сумма сделки" AS VARCHAR),
                         '[\\s\u00a0]', '', 'g') AS DOUBLE) AS amount_uzs,
                TRY_CAST(regexp_replace(CAST(d."Стартовая цена" AS VARCHAR),
                         '[\\s\u00a0]', '', 'g') AS DOUBLE) AS start_price_uzs,
                d."Номер контракта" AS contract_id,
                d."Наименование товара" AS product_full,
                d."Единица измерения" AS unit,
                d."Регион" AS region,
                d."Тип контракта" AS contract_type,
                d."Форма контракта" AS contract_form,
                d."Состояние сделки" AS status,
                d."ИНН продавца" AS seller_inn,
                d."ИНН покупателя" AS buyer_inn,
                d."Брокер продавца" AS seller_broker_code,
                d."Брокер покупателя" AS buyer_broker_code,
                d."Дата оплаты" AS payment_date,
                d."Дата поставки" AS delivery_date,
                d."Поставлено" AS delivered_qty
            FROM deals d
        )
        SELECT
            b.deal_id, b.deal_date,
            EXTRACT(YEAR FROM b.deal_date)::INTEGER AS year,
            EXTRACT(MONTH FROM b.deal_date)::INTEGER AS month,
            EXTRACT(QUARTER FROM b.deal_date)::INTEGER AS quarter,
            b.deal_time, b.trade_type, b.quantity, b.amount_uzs,
            ROUND(b.amount_uzs / r."Курс", 2) AS amount_usd,
            b.start_price_uzs, b.contract_id,
            COALESCE(c.product_group, b.product_full) AS product,
            b.product_full, c.category, c.industry,
            b.unit, b.region, b.contract_type, b.contract_form, b.status,
            (b.status LIKE 'Исполнен%') AS is_executed,
            (b.status LIKE 'Аннулирован%') AS is_cancelled,
            b.seller_inn, ps.name AS seller_name,
            b.buyer_inn, pb.name AS buyer_name,
            b.seller_broker_code, bs."Наименование" AS seller_broker_name,
            b.buyer_broker_code, bb."Наименование" AS buyer_broker_name,
            b.payment_date, b.delivery_date, b.delivered_qty
        FROM base b
        ASOF LEFT JOIN usd_rates r ON b.deal_date >= r."Дата"
        LEFT JOIN p ps ON ps.inn = b.seller_inn
        LEFT JOIN p pb ON pb.inn = b.buyer_inn
        LEFT JOIN c ON c.contract_id = b.contract_id
        LEFT JOIN brokers bs ON bs."Код брокера" = b.seller_broker_code
        LEFT JOIN brokers bb ON bb."Код брокера" = b.buyer_broker_code
    """)
    # Bir mahsulotning turli yozilishlarini (BENZIN / Бензин, "Хлопок-сырец" /
    # "Хлопок сырец") bitta nomga birlashtiramiz: eng ko'p uchraydigan,
    # BOSH HARFLI emas variant tanlanadi.
    connection.execute("""
        CREATE TEMP TABLE product_map AS
        WITH variants AS (
            SELECT product AS raw, COUNT(*) AS n,
                   trim(regexp_replace(
                       regexp_replace(lower(product), '[-–—_/]', ' ', 'g'),
                       '\\s+', ' ', 'g')) AS key
            FROM v_deals WHERE product IS NOT NULL GROUP BY product
        )
        SELECT raw,
               arg_max(raw, n + CASE WHEN raw <> upper(raw) THEN 1000000000 ELSE 0 END)
                   OVER (PARTITION BY key) AS canonical
        FROM variants
    """)
    connection.execute("""
        UPDATE v_deals SET product = m.canonical
        FROM product_map m WHERE v_deals.product = m.raw
    """)
    n = connection.execute("SELECT COUNT(*) FROM v_deals").fetchone()[0]
    print(f"v_deals (tahlil jadvali) yaratildi: {n} ta qator")


def ensure_database():
    """Baza yo'q bo'lsa, CSV fayllardan avtomatik yaratadi."""
    if not DB_PATH.exists():
        create_database()


def get_connection():
    ensure_database()
    return duckdb.connect(str(DB_PATH), read_only=True)


def create_database():
    # Kerakli CSV fayllar mavjudligini tekshiramiz
    required_files = [
        "contracts.csv",
        "participants.csv",
        "brokers.csv",
        "usd_rates.csv"
    ]

    for file_name in required_files:
        file_path = DATA_DIR / file_name

        if not file_path.exists():
            raise FileNotFoundError(
                f"Fayl topilmadi: {file_path}"
            )

    # 2022–2026 yillardagi bitim fayllarini tekshiramiz
    deal_files = list(DATA_DIR.glob("deals_*.csv"))

    if not deal_files:
        raise FileNotFoundError(
            "deals_2022.csv kabi bitim fayllari topilmadi."
        )

    # Database bilan ulanish
    connection = duckdb.connect(str(DB_PATH))

    try:
        # Har bir jadvalni CSV fayldan yaratamiz
        tables = {
            "deals": str(DATA_DIR / "deals_*.csv"),
            "contracts": str(DATA_DIR / "contracts.csv"),
            "participants": str(DATA_DIR / "participants.csv"),
            "brokers": str(DATA_DIR / "brokers.csv"),
            "usd_rates": str(DATA_DIR / "usd_rates.csv")
        }

        for table_name, csv_path in tables.items():
            # Oldingi jadval mavjud bo'lsa, o'chiramiz
            connection.execute(
                f"DROP TABLE IF EXISTS {table_name}"
            )

            # CSV fayldan yangi jadval yaratamiz
            relation = connection.from_csv_auto(
                csv_path,
                header=True,
                delimiter=",",
                union_by_name=True
            )

            relation.create(table_name)

            print(f"{table_name} jadvali yaratildi.")

        # Har bir jadvaldagi qatorlar sonini chiqaramiz
        print("\n--- DATABASE STATISTICS ---")

        for table_name in tables:
            result = connection.execute(
                f"SELECT COUNT(*) FROM {table_name}"
            ).fetchone()

            print(f"{table_name}: {result[0]} ta qator")

        build_analytics_table(connection)

        print("\nDatabase muvaffaqiyatli yaratildi!")

    finally:
        connection.close()


if __name__ == "__main__":
    create_database()

