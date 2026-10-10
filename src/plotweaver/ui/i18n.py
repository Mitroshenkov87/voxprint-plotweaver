"""UI strings. English is the default. Russian and German cover the same keys."""

from __future__ import annotations

import os

STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "app": "Voxprint AI Plotweaver",
        "new": "New book",
        "subtitle": "A synopsis in. A novel out. Local models only.",
        "title": "Title",
        "author": "Author",
        "language": "Language",
        "synopsis": "Synopsis",
        "references": "Reference books (structure and style only)",
        "add_ref": "Add reference",
        "dark": "Dark/mature themes",
        "tier": "Model tier",
        "tier_standard": "Standard",
        "tier_least_censored": "Least censored",
        "words": "Target words",
        "chapters": "Chapters (0 = automatic)",
        "formats": "Export",
        "export_epub": "EPUB 3 (default)",
        "export_fb2": "FictionBook 2.1",
        "export_docx": "DOCX",
        "export_markdown": "Markdown",
        "export_marks": "Speaker marks (legacy)",
        "sound_markup": "Add sound markup",
        "mode": "Mode",
        "start": "Write the book",
        "approve": "Approve and continue",
        "progress": "Progress",
        "result": "Result",
        "back": "Back",
        "mock": "Mock model (no GPU)",
        "waiting": "Waiting for approval",
        "done": "Export is ready",
        "egg": "The loom is awake.",
        "gpu_note": "A real run needs an NVIDIA RTX 40-series GPU or newer.",
        "settings": "Settings",
        "settings_vram_tier": "VRAM tier",
        "settings_vram_auto": "Auto",
        "settings_vram_16": "16 GB",
        "settings_vram_24": "24 GB",
        "settings_vram_note": (
            "Detected {detected}. Active tier: {chosen}. "
            "A card under 24 GB keeps 2 GB free. A 24 GB card keeps 3 GB free."
        ),
        "settings_vram_blocked": "The 24 GB tier needs a card that can run it.",
        "settings_uncensored": "Download abliterated models",
        "settings_uncensored_note": (
            "The default install is stock models only. Abliterated models are a separate download."
        ),
        "settings_uncensored_blocked": ("No published least-censored model fits this card."),
        "settings_download": "Download",
        "settings_downloading": "Downloading…",
        "settings_save": "Save",
        "settings_saved": "Saved.",
    },
    "ru": {
        "app": "Voxprint AI Plotweaver",
        "new": "Новая книга",
        "subtitle": "Синопсис на входе. Роман на выходе. Только локальные модели.",
        "title": "Название",
        "author": "Автор",
        "language": "Язык",
        "synopsis": "Синопсис",
        "references": "Книги-образцы (только структура и стиль)",
        "add_ref": "Добавить образец",
        "dark": "Тёмные и взрослые темы",
        "tier": "Класс модели",
        "tier_standard": "Обычная",
        "tier_least_censored": "Наименее цензурированная",
        "words": "Объём, слов",
        "chapters": "Глав (0 = само)",
        "formats": "Экспорт",
        "export_epub": "EPUB 3 (по умолчанию)",
        "export_fb2": "FictionBook 2.1",
        "export_docx": "DOCX",
        "export_markdown": "Markdown",
        "export_marks": "Метки дикторов (прежний формат)",
        "sound_markup": "Добавить звуковую разметку",
        "mode": "Режим",
        "start": "Написать книгу",
        "approve": "Утвердить и продолжить",
        "progress": "Ход работы",
        "result": "Результат",
        "back": "Назад",
        "mock": "Учебная модель (без GPU)",
        "waiting": "Ждёт утверждения",
        "done": "Экспорт готов",
        "egg": "Станок проснулся.",
        "gpu_note": "Настоящий запуск требует NVIDIA RTX 40-й серии или новее.",
        "settings": "Настройки",
        "settings_vram_tier": "Уровень видеопамяти",
        "settings_vram_auto": "Авто",
        "settings_vram_16": "16 ГБ",
        "settings_vram_24": "24 ГБ",
        "settings_vram_note": (
            "Обнаружено {detected}. Активный уровень: {chosen}. "
            "На карте меньше 24 ГБ остаётся 2 ГБ. На карте 24 ГБ остаётся 3 ГБ."
        ),
        "settings_vram_blocked": "Уровень 24 ГБ доступен только на карте, которая его тянет.",
        "settings_uncensored": "Скачать аблитерированные модели",
        "settings_uncensored_note": (
            "По умолчанию только обычные модели. Аблитерированные скачиваются отдельно."
        ),
        "settings_uncensored_blocked": (
            "Для этой карты нет опубликованной наименее цензурированной модели."
        ),
        "settings_download": "Скачать",
        "settings_downloading": "Скачивание…",
        "settings_save": "Сохранить",
        "settings_saved": "Сохранено.",
    },
    "de": {
        "app": "Voxprint AI Plotweaver",
        "new": "Neues Buch",
        "subtitle": "Eine Synopsis hinein. Ein Roman heraus. Nur lokale Modelle.",
        "title": "Titel",
        "author": "Autor",
        "language": "Sprache",
        "synopsis": "Synopsis",
        "references": "Referenzbücher (nur Struktur und Stil)",
        "add_ref": "Referenz hinzufügen",
        "dark": "Düstere und erwachsene Themen",
        "tier": "Modellstufe",
        "tier_standard": "Standard",
        "tier_least_censored": "Am wenigsten zensiert",
        "words": "Zielwörter",
        "chapters": "Kapitel (0 = automatisch)",
        "formats": "Export",
        "export_epub": "EPUB 3 (Standard)",
        "export_fb2": "FictionBook 2.1",
        "export_docx": "DOCX",
        "export_markdown": "Markdown",
        "export_marks": "Sprechermarken (ältere Form)",
        "sound_markup": "Klangmarkierung hinzufügen",
        "mode": "Modus",
        "start": "Buch schreiben",
        "approve": "Freigeben und weiter",
        "progress": "Fortschritt",
        "result": "Ergebnis",
        "back": "Zurück",
        "mock": "Ersatzmodell (ohne GPU)",
        "waiting": "Wartet auf Freigabe",
        "done": "Export ist fertig",
        "egg": "Der Webstuhl ist wach.",
        "gpu_note": "Ein echter Lauf braucht eine NVIDIA RTX 40 oder neuer.",
        "settings": "Einstellungen",
        "settings_vram_tier": "VRAM-Stufe",
        "settings_vram_auto": "Automatisch",
        "settings_vram_16": "16 GB",
        "settings_vram_24": "24 GB",
        "settings_vram_note": (
            "Erkannt: {detected}. Aktive Stufe: {chosen}. "
            "Unter 24 GB bleiben 2 GB frei. Ab 24 GB bleiben 3 GB frei."
        ),
        "settings_vram_blocked": "Die 24-GB-Stufe braucht eine Karte, die sie ausführen kann.",
        "settings_uncensored": "Abliterierte Modelle herunterladen",
        "settings_uncensored_note": (
            "Standard sind nur die Originalmodelle. Abliterierte Modelle sind ein eigener Download."
        ),
        "settings_uncensored_blocked": (
            "Für diese Karte passt kein veröffentlichtes am wenigsten zensiertes Modell."
        ),
        "settings_download": "Herunterladen",
        "settings_downloading": "Wird geladen…",
        "settings_save": "Speichern",
        "settings_saved": "Gespeichert.",
    },
}


def ui_language() -> str:
    raw = os.environ.get("PLOTWEAVER_LANG", "en").lower()
    if raw in STRINGS:
        return raw
    return "en"


def tr(key: str, language: str | None = None) -> str:
    catalog = STRINGS[language or ui_language()]
    return catalog.get(key, STRINGS["en"][key])
