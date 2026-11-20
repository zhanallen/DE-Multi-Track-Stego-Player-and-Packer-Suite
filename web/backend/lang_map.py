"""Language code -> display name table.

Copied from ``src/player_app.py`` (LANGUAGE_MAP) because importing player_app
would pull in PySide6. Keep the two tables in sync when adding languages.
"""

LANGUAGE_MAP = {
    'ar': '🇸🇦 العربية (Arabic)',
    'bn': '🇧🇩 বাংলা (Bengali)',
    'de-DE': '🇩🇪 Deutsch (German)',
    'en': '🇬🇧 English (UK)',
    'en-US': '🇺🇸 English (United States)',
    'es-US': '🇪🇸 Español (Spanish - US)',
    'fr-FR': '🇫🇷 Français (French)',
    'hi': '🇮🇳 हिन्दी (Hindi)',
    'id': '🇮🇩 Bahasa Indonesia (Indonesian)',
    'it': '🇮🇹 Italiano (Italian)',
    'iw': '🇮🇱 עברית (Hebrew)',
    'ja': '🇯🇵 日本語 (Japanese)',
    'ko': '🇰🇷 한국어 (Korean)',
    'ml': '🇮🇳 Malayalam (Malayalam)',
    'nl-NL': '🇳🇱 Nederlands (Dutch)',
    'pl': '🇵🇱 Polski (Polish)',
    'pt-BR': '🇧🇷 Português (Portuguese - Brazil)',
    'ru': '🇷🇺 Русский (Russian)',
    'ta': '🇮🇳 தமிழ் (Tamil)',
    'te': '🇮🇳 తెలుగు (Telugu)',
    'uk': '🇺🇦 Українська (Ukrainian)',
    'zh-TW': '🇹🇼 繁體中文 (Traditional Chinese)',
    'zh-CN': '🇨🇳 简体中文 (Simplified Chinese)',
    'zh': '🌐 中文 (Chinese)',
}


def get_display_name(lang: str) -> str:
    """Return the flag + name label for a track language, or a generic label."""
    return LANGUAGE_MAP.get(lang, f"({lang}) Track")
