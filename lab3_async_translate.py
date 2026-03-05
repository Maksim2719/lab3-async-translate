import asyncio
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
