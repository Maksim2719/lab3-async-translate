import asyncio
import re
import time
from pathlib import Path

import httpx
from googletrans import Translator, LANGUAGES

FILE_NAME = "steve_jobs.txt"
TARGET_LANG = "Irish"  # Irish -> ga

DEFAULT_TEXT = """Читачеві вирішувати, вдалося мені досягти цієї мети чи ні. Впевнений, що в цій драмі були персонажі, яким описані мною події запам’яталися дещо інакше, або ж вони вважатимуть, що я час від часу потрапляв у пастку «альтернативної реальності» Джобса. Коли я писав книжку про Генрі Кіссинджера — що стало для мене непоганою підготовкою до цього проекту, — мені також часто траплялося розмовляти з людьми, які виношували дуже гостро позитивні чи то гостро негативні емоції щодо головного героя. І це лише доводить теорію про суб’єктивність людського сприйняття, знаної як «ефект Расьомона». Але я старався якомога справедливіше передати бачення ситуацій конфліктуючих сторін, а також відкрито показувати джерела, з яких надійшла та чи інша інформація."""

# Твій робочий домен
SERVICE_URL = "translate.google.com"

# Fallback endpoint (той самий домен!)
GTX_ENDPOINT = "https://translate.google.com/translate_a/single"

# анти-ліміт
TIMEOUT_SEC = 20.0
SYNC_DELAY_SEC = 0.8
ASYNC_STAGGER_SEC = 0.7
ASYNC_CONCURRENCY = 2
RETRIES = 2


def _translator() -> Translator:
    return Translator(service_urls=[SERVICE_URL])


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
    """
    Якщо назва -> код, якщо код -> назва.
    """
    if not isinstance(lang, str) or not lang.strip():
        return "Помилка: порожній параметр lang."
    s = lang.strip()

    code = s.lower()
    if code in LANGUAGES:
        return LANGUAGES[code].title()

    inv = {name.lower(): code for code, name in LANGUAGES.items()}
    if s.lower() in inv:
        return inv[s.lower()]

    return f"Помилка: невідома мова '{lang}'."


# ---- fallback translate via gtx (translate.google.com) ----
def _gtx_translate_sync(text: str, tl: str) -> str:
    params = {"client": "gtx", "sl": "auto", "tl": tl, "dt": "t", "q": text}
    headers = {"User-Agent": "Mozilla/5.0"}
    with httpx.Client(timeout=TIMEOUT_SEC, headers=headers) as client:
        r = client.get(GTX_ENDPOINT, params=params)
        r.raise_for_status()
        data = r.json()
    return "".join(chunk[0] for chunk in data[0] if chunk and chunk[0])


async def _gtx_translate_async(text: str, tl: str, client: httpx.AsyncClient) -> str:
    params = {"client": "gtx", "sl": "auto", "tl": tl, "dt": "t", "q": text}
    r = await client.get(GTX_ENDPOINT, params=params)
    r.raise_for_status()
    data = r.json()
    return "".join(chunk[0] for chunk in data[0] if chunk and chunk[0])


# ===== 3.2 LangDetect(txt) =====
def LangDetect(txt: str):
    """
    Повертає (lang_code, confidence). confidence може бути None — це нормально.
    Щоб detect не ламався на довгому тексті, беремо короткий семпл.
    """
    if not isinstance(txt, str) or not txt.strip():
        return "", None

    sample = txt.strip()[:250]  # семпл для стабільності
    t = _translator()

    for _ in range(RETRIES):
        try:
            d = t.detect(sample)
            return d.lang, d.confidence
        except Exception:
            time.sleep(0.35)

    # fallback: витягнемо src із відповіді translate_a/single
    try:
        params = {"client": "gtx", "sl": "auto", "tl": "en", "dt": "t", "q": sample}
        headers = {"User-Agent": "Mozilla/5.0"}
        with httpx.Client(timeout=TIMEOUT_SEC, headers=headers) as client:
            r = client.get(GTX_ENDPOINT, params=params)
            r.raise_for_status()
            data = r.json()
        src = data[2] if len(data) > 2 else ""
        return src, None
    except Exception:
        return "", None


# ===== 3.1 TransLate(str, lang) =====
def TransLate(text: str, lang: str) -> str:
    """
    Повертає переклад або повідомлення про помилку.
    """
    if not isinstance(text, str) or not text.strip():
        return "Помилка: порожній текст для перекладу."

    tl = _to_lang_code(lang)
    if not tl:
        return f"Помилка: невідома мова перекладу '{lang}'."

    t = _translator()

    # 1) пробуємо googletrans
    for _ in range(RETRIES):
        try:
            return t.translate(text, dest=tl).text
        except Exception:
            time.sleep(0.35)

    # 2) fallback gtx (translate.google.com)
    for _ in range(RETRIES):
        try:
            return _gtx_translate_sync(text, tl)
        except Exception as e:
            last = e
            time.sleep(0.35)

    return f"Помилка перекладу: {type(last).__name__}: {last}"


# ===== 3.4.1 SYNC =====
def run_sync(full_text: str, TxtList: list[str], target_lang: str):
    start = time.perf_counter()

    orig_code, orig_conf = LangDetect(full_text)

    translated = []
    for i, s in enumerate(TxtList):
        translated.append(TransLate(s, target_lang))
        if i != len(TxtList) - 1:
            time.sleep(SYNC_DELAY_SEC)

    elapsed = time.perf_counter() - start
    return orig_code, orig_conf, " ".join(translated), elapsed


# ===== 3.4.2 ASYNC =====
async def run_async(full_text: str, TxtList: list[str], target_lang: str):
    start = time.perf_counter()
    sem = asyncio.Semaphore(ASYNC_CONCURRENCY)

    tl = _to_lang_code(target_lang)
    headers = {"User-Agent": "Mozilla/5.0"}

    async def translate_one(i: int, sentence: str, client: httpx.AsyncClient) -> str:
        await asyncio.sleep(i * ASYNC_STAGGER_SEC)
        async with sem:
            # 1) googletrans у потоці
            try:
                t = _translator()
                return await asyncio.to_thread(lambda: t.translate(sentence, dest=tl).text)
            except Exception:
                # 2) fallback gtx
                return await _gtx_translate_async(sentence, tl, client)

    detect_task = asyncio.to_thread(LangDetect, full_text)

    async with httpx.AsyncClient(timeout=TIMEOUT_SEC, headers=headers) as client:
        translate_tasks = [translate_one(i, s, client) for i, s in enumerate(TxtList)]
        (orig_code, orig_conf), translated = await asyncio.gather(detect_task, asyncio.gather(*translate_tasks))

    elapsed = time.perf_counter() - start
    return orig_code, orig_conf, " ".join(translated), elapsed


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
    orig_code_s, orig_conf_s, tr_s, t_sync = run_sync(text, TxtList, TARGET_LANG)
    orig_name_s = CodeLang(orig_code_s) if orig_code_s else "невідомо"
    conf_print = orig_conf_s if orig_conf_s is not None else "—"
    print(f"Мова оригінального тексту: {orig_name_s} | код: {orig_code_s or '—'} | confidence: {conf_print}")

    print("\nОРИГІНАЛЬНИЙ ТЕКСТ:")
    print(text.strip())

    print(f"\nМова перекладу: {target_name} | код: {target_code or '—'}")

    print("\nПЕРЕКЛАД ТЕКСТУ (SYNC):")
    print(tr_s)

    print(f"\nЧас (визначення мови + переклад) SYNC: {t_sync:.4f} c")

    # ASYNC
    orig_code_a, orig_conf_a, tr_a, t_async = asyncio.run(run_async(text, TxtList, TARGET_LANG))
    print(f"Час (визначення мови + переклад) ASYNC: {t_async:.4f} c")


if __name__ == "__main__":
    main()