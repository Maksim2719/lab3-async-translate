import asyncio
<<<<<<< HEAD
import os
import re
import sys
import time
from typing import Dict, List, Optional, Tuple

from googletrans import Translator

# Спроба отримати вбудований словник мов (код -> назва англійською)
try:
    from googletrans import LANGUAGES  # code -> name
except Exception:
    LANGUAGES = {}


def _norm(s: str) -> str:
    """Нормалізація рядка: прибрати пробіли + зробити нижній регістр."""
    return (s or "").strip().lower()


def CodeLang(lang: str) -> str:
    """
    Перетворення мови:
    - якщо передали назву (English/Irish) -> повертає код (en/ga)
    - якщо передали код (en/ga/zh-cn) -> повертає назву (english/irish)
    """
    token = _norm(lang)
    if not token:
        return "Помилка: порожній параметр lang"

    # Підготуємо словники: code->name і name->code
    code_to_name: Dict[str, str] = {k.lower(): v.lower() for k, v in (LANGUAGES or {}).items()}
    name_to_code: Dict[str, str] = {}
    for c, n in code_to_name.items():
        name_to_code.setdefault(n, c)

    # Якщо це схоже на код (en, ga, zh-cn) -> шукаємо назву
    if re.fullmatch(r"[a-z]{2,3}(-[a-z]{2,4})?", token):
        return code_to_name.get(token, f"Помилка: невідомий код мови '{lang}'")

    # Інакше вважаємо, що це назва -> шукаємо код
    return name_to_code.get(token, f"Помилка: невідома назва мови '{lang}'")


def LangDetect(txt: str) -> Tuple[str, str, Optional[float]]:
    """
    Визначення мови тексту.
    Повертає: (назва_мови, код_мови, confidence або None)
    """
    try:
        tr = Translator()
        det = tr.detect(txt)

        code = getattr(det, "lang", "unknown")
        conf = getattr(det, "confidence", None)
        conf = float(conf) if conf is not None else None

        name = CodeLang(code)
        if isinstance(name, str) and name.startswith("Помилка"):
            name = "unknown"

        return name, code, conf
    except Exception:
        return "Помилка", "Помилка", None


def TransLate(s: str, lang: str) -> str:
    """
    Переклад рядка s на мову lang.
    lang може бути назвою (Irish) або кодом (ga).
    """
    try:
        token = _norm(lang)
        if not token:
            return "Помилка: порожній параметр lang"

        # Визначаємо код мови призначення
        if re.fullmatch(r"[a-z]{2,3}(-[a-z]{2,4})?", token):
            dest = token
        else:
            dest = CodeLang(lang)
            if dest.startswith("Помилка"):
                return dest

        tr = Translator()
        res = tr.translate(s, dest=dest)
        return getattr(res, "text", "") or ""
    except Exception as e:
        return f"Помилка перекладу: {e}"


def split_sentences(text: str) -> List[str]:
    """Розбиття тексту на речення (кожен елемент списку TxtList — одне речення)."""
    text = (text or "").strip()
    if not text:
        return []
    text = re.sub(r"\s+", " ", text)
    parts = re.split(r"(?<=[\.\!\?\…])\s+", text)
    return [p.strip() for p in parts if p and p.strip()]


def read_file(path: str) -> Tuple[Optional[str], str]:
    """Читання тексту з файлу (UTF-8)."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return None, f.read()
    except Exception as e:
        return f"Помилка читання файлу '{path}': {e}", ""


def _dest_name_code(dest_lang: str) -> Tuple[str, str]:
    """Допоміжно: отримати (назва, код) для мови перекладу."""
    token = _norm(dest_lang)

    # Якщо ввели код
    if re.fullmatch(r"[a-z]{2,3}(-[a-z]{2,4})?", token):
        code = token
        name = CodeLang(code)
        if name.startswith("Помилка"):
            name = "unknown"
        return name, code

    # Якщо ввели назву
    code = CodeLang(dest_lang)
    name = token
    if code.startswith("Помилка"):
        code = "unknown"
    return name, code


def sync_work(TxtList: List[str], dest_lang: str) -> Tuple[List[str], float]:
    """
    3.4.1 — синхронно: послідовно detect + translate для кожного речення.
    Повертає (список перекладів, час).
    """
    t0 = time.perf_counter()
    out: List[str] = []
    for s in TxtList:
        LangDetect(s)                 # вимога: визначення мови
        out.append(TransLate(s, dest_lang))  # переклад
    return out, time.perf_counter() - t0


async def _one_async(s: str, dest_lang: str, sem: asyncio.Semaphore) -> str:
    """Один асинхронний “воркер” для речення (обмеження паралельності семафором)."""
    async with sem:
        # googletrans синхронний, тому викликаємо у фоновому потоці
        await asyncio.to_thread(LangDetect, s)
        return await asyncio.to_thread(TransLate, s, dest_lang)


async def async_work(TxtList: List[str], dest_lang: str, concurrency: int = 10) -> Tuple[List[str], float]:
    """
    3.4.2 — асинхронно: одночасно запускаємо detect+translate для всіх речень.
    Повертає (список перекладів, час).
    """
    t0 = time.perf_counter()
    sem = asyncio.Semaphore(max(1, int(concurrency)))
    tasks = [asyncio.create_task(_one_async(s, dest_lang, sem)) for s in TxtList]
    out = await asyncio.gather(*tasks)
    return list(out), time.perf_counter() - t0


def parse_args() -> Tuple[str, str]:
    """
    Параметри запуску:
    - без параметрів: steve_jobs_variant10.txt + Irish
    - python -m lab3_async_translate 10 Irish
    - python -m lab3_async_translate steve_jobs_variant10 Irish   (без .txt можна)
    """
    default_file = "steve_jobs_variant10.txt"
    default_lang = "Irish"   # варіант 10

    if len(sys.argv) == 1:
        return default_file, default_lang

    a1 = sys.argv[1].strip()

    # якщо ввели номер варіанту (наприклад: 10)
    if a1.isdigit():
        v = int(a1)
        filename = f"steve_jobs_variant{v}.txt"
        lang = default_lang if len(sys.argv) < 3 else sys.argv[2].strip()
        return filename, lang

    # якщо ввели назву файлу (можна без .txt)
    filename = a1
    if not filename.lower().endswith(".txt"):
        filename += ".txt"

    lang = default_lang if len(sys.argv) < 3 else sys.argv[2].strip()
    return filename, lang


def print_report(filename: str, text: str, TxtList: List[str], dest_lang: str) -> None:
    """
    Вивід результатів за вимогою 3.5:
    файл, символи, речення, мова/код/confidence, оригінал, мова перекладу.
    """
    src_name, src_code, src_conf = LangDetect(text)
    dest_name, dest_code = _dest_name_code(dest_lang)
    conf_str = "N/A" if src_conf is None else f"{src_conf:.6f}"

    print("\nЛР №3 | Асинхронний переклад (googletrans)\n")
    print(f"Файл: {filename}")
    print(f"Символів: {len(text)} | Речень: {len(TxtList)}")
    print(f"Оригінал: {src_name} ({src_code}), confidence: {conf_str}")
    print(f"Переклад на: {dest_name} ({dest_code})")
    print("\nОригінальний текст:\n" + text)


async def main() -> int:
    """Головна функція: читання файлу -> TxtList -> sync/async переклад -> час."""
    filename, dest_lang = parse_args()

    if not os.path.exists(filename):
        print(f"Файл не знайдено: {filename}")
        print("Приклад: python -m lab3_async_translate steve_jobs_variant10 Irish")
        print("Або:     python -m lab3_async_translate 10 Irish")
        return 1

    err, text = read_file(filename)
    if err:
        print(err)
        return 1

    TxtList = split_sentences(text)

    print_report(filename, text, TxtList, dest_lang)

    # 3.4.1 — синхронно
    tr_sync, t_sync = sync_work(TxtList, dest_lang)
    print("\n--- Переклад (синхронно) ---\n" + " ".join(tr_sync))
    print(f"\nЧас синхронно (detect+translate): {t_sync:.6f} сек")

    # 3.4.2 — асинхронно
    tr_async, t_async = await async_work(TxtList, dest_lang, concurrency=10)
    print("\n--- Переклад (асинхронно) ---\n" + " ".join(tr_async))
    print(f"\nЧас асинхронно (detect+translate): {t_async:.6f} сек\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
=======
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
>>>>>>> 7a07637301d0ba9c599f97815ee80d57320699e3
