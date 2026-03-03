import asyncio
import re
import time
from pathlib import Path

from googletrans import Translator, LANGUAGES


FILE_NAME = "steve_jobs.txt"
TARGET_LANG = "Irish"  # Irish -> ga (можна також просто "ga")

DEFAULT_TEXT = """Читачеві вирішувати, вдалося мені досягти цієї мети чи ні. Впевнений, що в цій драмі були персонажі, яким описані мною події запам’яталися дещо інакше, або ж вони вважатимуть, що я час від часу потрапляв у пастку «альтернативної реальності» Джобса. Коли я писав книжку про Генрі Кіссинджера — що стало для мене непоганою підготовкою до цього проекту, — мені також часто траплялося розмовляти з людьми, які виношували дуже гостро позитивні чи то гостро негативні емоції щодо головного героя. І це лише доводить теорію про суб’єктивність людського сприйняття, знаної як «ефект Расьомона». Але я старався якомога справедливіше передати бачення ситуацій конфліктуючих сторін, а також відкрито показувати джерела, з яких надійшла та чи інша інформація."""

# Починаємо з translate.google.com (у тебе воно 100% працює на 1 запиті),
# а далі маємо fallback.
SERVICE_URLS = [
    "translate.google.com",
    "translate.googleapis.com",
    "translate.google.ie",
    "translate.google.co.uk",
]


def _make_translator(url: str) -> Translator:
    return Translator(service_urls=[url])


def _split_sentences(text: str) -> list[str]:
    cleaned = " ".join(text.replace("\n", " ").split()).strip()
    if not cleaned:
        return []
    parts = re.split(r"(?<=[.!?…])\s+", cleaned)
    return [p.strip() for p in parts if p.strip()]


def _to_lang_code(lang: str) -> str:
    if not isinstance(lang, str) or not lang.strip():
        return ""
    s = lang.strip()
    if s.lower() in LANGUAGES:
        return s.lower()
    inv = {name.lower(): code for code, name in LANGUAGES.items()}
    return inv.get(s.lower(), "")


# ===== 3.3 CodeLang(lang) =====
def CodeLang(lang: str) -> str:
    """Якщо назва -> код, якщо код -> назва."""
    if not isinstance(lang, str) or not lang.strip():
        return "Помилка: порожній параметр lang."
    s = lang.strip()

    code = s.lower()
    if code in LANGUAGES:
        return LANGUAGES[code].title()  # код -> назва

    inv = {name.lower(): code for code, name in LANGUAGES.items()}
    if s.lower() in inv:
        return inv[s.lower()]  # назва -> код

    return f"Помилка: невідома мова '{lang}'."


# ===== 3.2 LangDetect(txt) =====
def LangDetect(txt: str):
    """Повертає (lang_code, confidence). Якщо не вдалось — ('', 0.0)."""
    if not isinstance(txt, str) or not txt.strip():
        return "", 0.0

    last_err = None
    for url in SERVICE_URLS:
        for _ in range(2):  # retry
            try:
                t = _make_translator(url)
                d = t.detect(txt)
                return d.lang, float(d.confidence)
            except Exception as e:
                last_err = e
                time.sleep(0.35)

    return "", 0.0


# ===== 3.1 TransLate(str, lang) =====
def TransLate(text, lang: str):
    """
    Повертає переклад або повідомлення про помилку.
    Підтримує:
      - text: str
      - text: list[str]  (batch переклад = менше запитів = стабільніше)
    """
    code = _to_lang_code(lang)
    if not code:
        return f"Помилка: невідома мова перекладу '{lang}'."

    if isinstance(text, str):
        if not text.strip():
            return "Помилка: порожній текст для перекладу."
    elif isinstance(text, list):
        if not text or not any(isinstance(x, str) and x.strip() for x in text):
            return ["Помилка: порожній текст для перекладу."] * (len(text) if isinstance(text, list) else 1)
    else:
        return "Помилка: некоректний тип text."

    last_err = None
    for url in SERVICE_URLS:
        for _ in range(2):  # retry
            try:
                t = _make_translator(url)
                res = t.translate(text, dest=code)  # <-- batch працює для list[str]
                if isinstance(text, list):
                    return [r.text for r in res]
                return res.text
            except Exception as e:
                last_err = e
                time.sleep(0.35)

    # якщо це список — повернемо список помилок
    if isinstance(text, list):
        return [f"Помилка перекладу: {type(last_err).__name__}: {last_err}"] * len(text)
    return f"Помилка перекладу: {type(last_err).__name__}: {last_err}"


def run_sync(full_text: str, TxtList: list[str], target_lang: str):
    start = time.perf_counter()

    orig_code, orig_conf = LangDetect(full_text)
    translated_list = TransLate(TxtList, target_lang)  # batch

    elapsed = time.perf_counter() - start
    return orig_code, orig_conf, translated_list, elapsed


async def run_async(full_text: str, TxtList: list[str], target_lang: str):
    start = time.perf_counter()

    detect_task = asyncio.to_thread(LangDetect, full_text)
    translate_task = asyncio.to_thread(TransLate, TxtList, target_lang)  # batch у фоні

    (orig_code, orig_conf), translated_list = await asyncio.gather(detect_task, translate_task)

    elapsed = time.perf_counter() - start
    return orig_code, orig_conf, translated_list, elapsed


def main():
    path = Path(FILE_NAME)
    if not path.exists():
        path.write_text(DEFAULT_TEXT, encoding="utf-8")

    try:
        text = path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"Ім'я файлу: {FILE_NAME}")
        print(f"Помилка читання файлу: {type(e).__name__}: {e}")
        return

    TxtList = _split_sentences(text)

    target_code = _to_lang_code(TARGET_LANG)
    target_name = CodeLang(target_code) if target_code else "невідомо"

    print(f"Ім'я файлу: {FILE_NAME}")
    print(f"Кількість символів в тексті: {len(text)}")
    print(f"Кількість речень в тексті: {len(TxtList)}")

    # SYNC
    orig_code_s, orig_conf_s, tr_s, time_s = run_sync(text, TxtList, TARGET_LANG)
    orig_name_s = CodeLang(orig_code_s) if orig_code_s else "невідомо"
    print(f"Мова оригінального тексту: {orig_name_s} | код: {orig_code_s or '—'} | confidence: {orig_conf_s if orig_conf_s else '—'}")

    print("\nОРИГІНАЛЬНИЙ ТЕКСТ:")
    print(text.strip())

    print(f"\nМова перекладу: {target_name} | код: {target_code or '—'}")

    print("\nПЕРЕКЛАД ТЕКСТУ (SYNC):")
    if isinstance(tr_s, list):
        print(" ".join(tr_s))
    else:
        print(tr_s)
    print(f"\nЧас (визначення мови + переклад) SYNC: {time_s:.4f} c")

    # ASYNC
    orig_code_a, orig_conf_a, tr_a, time_a = asyncio.run(run_async(text, TxtList, TARGET_LANG))
    print(f"Час (визначення мови + переклад) ASYNC: {time_a:.4f} c")


if __name__ == "__main__":
    main()