"""Loyiha sozlamalari. Qiymatlar .env fayldan yoki muhit o'zgaruvchilaridan olinadi."""
import os

from dotenv import load_dotenv

load_dotenv()

# Gemini API kaliti (https://aistudio.google.com/apikey)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Ishlatiladigan model. Kerak bo'lsa .env da GEMINI_MODEL=... deb o'zgartiring.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")

# Suhbat tarixidan AI ga yuboriladigan oxirgi xabarlar soni
MAX_HISTORY_MESSAGES = 8
