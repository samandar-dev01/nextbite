import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

from config import GEMINI_MODEL

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    print("XATO: API key topilmadi!")
    raise SystemExit

print("API key topildi.")
print("API key uzunligi:", len(api_key))

client = genai.Client(api_key=api_key)

try:
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents="Salom! Faqat OK deb javob ber."
    )

    print("Gemini javobi:", response.text)

except Exception as e:
    print("Gemini xatosi:", repr(e))
