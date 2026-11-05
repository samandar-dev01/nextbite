# 📈 Birja AI — O'zbekiston birja bitimlari tahlili

500 000 ta birja bitimi (2022-01-03 … 2026-10-30) bo'yicha **interaktiv dashboard** va
**AI tahlilchi**. Savolni oddiy tilda (o'zbek / rus / ingliz) yozasiz — AI ma'lumotlar
bazasidan haqiqiy raqamlarni olib, jadval, grafik va xulosa bilan javob beradi.

## Imkoniyatlar

- **Dashboard**: savdo hajmi (UZS va USD), bitimlar soni, ishtirokchilar, bekor qilish ulushi;
  oyma-oy dinamika, yillik o'sish, hududlar, mahsulot toifalari, top mahsulot/kompaniya/broker.
  Yil bo'yicha filtr.
- **AI yordamchi** (Gemini + function calling):
  - istalgan kesimda reyting va statistika (hudud, mahsulot, kompaniya, broker, savdo turi, davr);
  - ikki davrni solishtirish (o'sish/pasayish %);
  - kompaniya / mahsulot / brokerni nomi bo'yicha qidirish, INN bo'yicha kartochka;
  - murakkab savollar uchun xavfsiz (faqat o'qish) SQL;
  - suhbat konteksti (oldingi savolga bog'langan savollar);
  - har javobda **ma'lumot manbasi** jadvali va avtomatik grafik.
- **Aniqlik**: AI raqamlarni o'ylab topmaydi — hamma son bazadan keladi. Summalar
  `Сумма сделки` (matn) dan songa o'giriladi, USD esa bitim kunidagi kurs bo'yicha hisoblanadi.

## Tez ishga tushirish

Talab: **Python 3.10+** va [Gemini API kaliti](https://aistudio.google.com/apikey).

```bash
cd backend

# 1. Virtual muhit va kutubxonalar
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 2. API kalit
cp .env.example .env              # so'ng .env ichiga GEMINI_API_KEY ni yozing

# 3. (ixtiyoriy) bazani qo'lda yaratish — server birinchi ishga tushganda o'zi yaratadi
python database.py

# 4. Serverni ishga tushirish
uvicorn main:app --reload
```

Brauzerda oching: **http://127.0.0.1:8000** (API hujjatlari: `/docs`).

> `GEMINI_API_KEY` bo'lmasa ham dashboard ishlaydi; faqat AI chat 503 xabar qaytaradi.

## Savol namunalari

- 2025-yilda eng ko'p savdo hajmiga ega 5 ta hudud qaysilar?
- Paxta savdosi yillar bo'yicha qanday o'zgargan?
- 2024 va 2025 yillarni savdo hajmi bo'yicha solishtir.
- Eng faol 10 ta broker va ularning ulushi.
- Какие регионы лидируют по объему торгов в 2026 году?

## Loyiha tuzilishi

```
backend/
├── main.py              # FastAPI: dashboard API, chat, frontend
├── config.py            # sozlamalar (.env: GEMINI_API_KEY, GEMINI_MODEL)
├── database.py          # CSV -> DuckDB, tahlil jadvali v_deals
├── services/
│   ├── analytics.py     # universal tahlil: guruhlash, filtr, solishtirish, SQL
│   ├── ai_agent.py      # Gemini agenti va vositalari
│   ├── market.py        # kompaniya / broker / mahsulot so'rovlari
│   └── statistics.py    # umumiy, yillik, holat statistikasi
├── static/index.html    # dashboard + chat interfeysi
└── data/                # CSV ma'lumotlar (deals_*.csv, contracts, participants, brokers, usd_rates)
```

## Ma'lumotlar bazasi

`database.py` CSV fayllardan DuckDB (`birja.duckdb`) yaratadi: `deals`, `contracts`,
`participants`, `brokers`, `usd_rates` va tahlil uchun tayyor **`v_deals`** jadvali
(inglizcha ustunlar, sonli summa, `amount_usd`, kompaniya/broker nomlari, mahsulot toifasi,
`is_executed` / `is_cancelled`). Ma'lumot yangilansa, `birja.duckdb` ni o'chirib qayta ishga tushiring.

## API (asosiylari)

| Endpoint | Tavsif |
|---|---|
| `GET /api/dashboard/summary?year=` | KPI ko'rsatkichlar |
| `GET /api/dashboard/monthly?year=` | oyma-oy dinamika |
| `GET /api/dashboard/yearly` | yillik hajm |
| `GET /api/dashboard/breakdown?by=region\|product\|category\|trade_type\|contract_type\|status` | kesim bo'yicha reyting |
| `GET /api/dashboard/top-companies?side=seller\|buyer` | top kompaniyalar |
| `GET /api/dashboard/top-brokers` | top brokerlar |
| `POST /api/chat` | `{question, language, history}` → `{answer, sources}` |

## Eslatmalar

- 2026-yil ma'lumoti 30-oktabrgacha — yillarni solishtirganda teng davrlarni oling.
- Savdo hajmi hisobida **bekor qilingan** (`Аннулирован…`) bitimlar chiqarib tashlanadi.
- `/api/chat` IP bo'yicha daqiqasiga 20 so'rov bilan cheklangan; SQL vositasi faqat o'qish rejimida.

## Deploy (internetga chiqarish)

Loyiha Docker bilan tayyor (`Dockerfile`, `render.yaml`). Baza image yaratilayotganda quriladi.

**Render.com (eng oson):**
1. Loyihani GitHub'ga yuklang (`.env` yuklanmaydi — `.gitignore` da).
2. Render → *New* → *Blueprint* → repozitoriyni tanlang (`render.yaml` avtomatik topiladi).
3. Panelda `GEMINI_API_KEY` qiymatini kiriting va deploy qiling.
4. Tayyor havola: `https://birja-ai.onrender.com`

**Boshqa platformalar** (Railway, Fly.io, Google Cloud Run): `Dockerfile` ni ishlating, `GEMINI_API_KEY` ni muhit o'zgaruvchisi qilib bering. Port `PORT` o'zgaruvchisidan olinadi.

> Ochiq serverda har bir AI savol sizning Gemini kvotangizdan ketadi. Chat IP bo'yicha daqiqasiga 20 so'rov bilan cheklangan; hakaton uchun yetarli.
