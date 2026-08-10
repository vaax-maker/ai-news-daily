"""briefer — production daily AI-briefing pipeline (VAAX AI BRIEFING).

Fetches today's daily-news doc from Firestore, converts it to 개조식 bullets via
OpenRouter, renders the mobile daily page + searchable archive, and (separately)
notifies Telegram with the infographic. See README.md for the full pipeline.
"""
