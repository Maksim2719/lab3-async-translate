import asyncio
import os
import re
import sys
import time
from typing import Dict, List, Optional, Tuple

from googletrans import Translator

try:
    from googletrans import LANGUAGES
except Exception:
    LANGUAGES = {}


def _norm(s: str) -> str:
    return (s or "").strip().lower()


def CodeLang(lang: str) -> str:
    # 3.3 CodeLang
    token = _norm(lang)
    if not token:
        return "Помилка: порожній параметр lang"

    code_to_name: Dict[str, str] = {
        k.lower(): v.lower() for k, v in (LANGUAGES or {}).items()
    }
    name_to_code: Dict[str, str] = {}

    for code, name in code_to_name.items():
        name_to_code.setdefault(name, code)

    if re.fullmatch(r"[a-z]{2,3}(-[a-z]{2,4})?", token):
        return code_to_name.get(token, f"Помилка: невідомий код мови '{lang}'")

    return name_to_code.get(token, f"Помилка: невідома назва мови '{lang}'")


async def LangDetect(txt: str) -> Tuple[str, str, Optional[float]]:
    # 3.2 LangDetect
    try:
        async with Translator() as tr:
            det = await tr.detect(txt)

        code = getattr(det, "lang", "unknown")
        conf = getattr(det, "confidence", None)
        conf = float(conf) if conf is not None else None

        name = CodeLang(code)
        if isinstance(name, str) and name.startswith("Помилка"):
            name = "unknown"

        return name, code, conf
    except Exception:
        return "Помилка", "Помилка", None


async def TransLate(s: str, lang: str) -> str:
    # 3.1 TransLate
    try:
        token = _norm(lang)
        if not token:
            return "Помилка: порожній параметр lang"

        if re.fullmatch(r"[a-z]{2,3}(-[a-z]{2,4})?", token):
            dest = token
        else:
            dest = CodeLang(lang)
            if dest.startswith("Помилка"):
                return dest

        async with Translator() as tr:
            res = await tr.translate(s, dest=dest)

        return getattr(res, "text", "") or ""
    except Exception as e:
        return f"Помилка перекладу: {e}"


def split_sentences(text: str) -> List[str]:
    text = (text or "").strip()
    if not text:
        return []

    text = re.sub(r"\s+", " ", text)
    parts = re.split(r"(?<=[.!?…])\s+", text)
    return [p.strip() for p in parts if p.strip()]


def read_file(path: str) -> Tuple[Optional[str], str]:
    # читання файлу
    try:
        with open(path, "r", encoding="utf-8") as f:
            return None, f.read()
    except Exception as e:
        return f"Помилка читання файлу '{path}': {e}", ""


def _dest_name_code(dest_lang: str) -> Tuple[str, str]:
    token = _norm(dest_lang)

    if re.fullmatch(r"[a-z]{2,3}(-[a-z]{2,4})?", token):
        code = token
        name = CodeLang(code)
        if isinstance(name, str) and name.startswith("Помилка"):
            name = "unknown"
        return name, code

    code = CodeLang(dest_lang)
    name = token
    if isinstance(code, str) and code.startswith("Помилка"):
        code = "unknown"

    return name, code


async def sync_work(TxtList: List[str], dest_lang: str) -> Tuple[List[str], float]:
    # 3.4.1 синхронно
    t0 = time.perf_counter()
    out: List[str] = []

    async with Translator() as tr:
        for s in TxtList:
            await tr.detect(s)
            res = await tr.translate(s, dest=_dest_name_code(dest_lang)[1])
            out.append(getattr(res, "text", "") or "")

    return out, time.perf_counter() - t0


async def _one_async(
    s: str, dest_code: str, sem: asyncio.Semaphore, tr: Translator
) -> str:
    async with sem:
        await tr.detect(s)
        res = await tr.translate(s, dest=dest_code)
        return getattr(res, "text", "") or ""


async def async_work(
    TxtList: List[str], dest_lang: str, concurrency: int = 10
) -> Tuple[List[str], float]:
    # 3.4.2 асинхронно
    t0 = time.perf_counter()
    sem = asyncio.Semaphore(max(1, int(concurrency)))
    dest_code = _dest_name_code(dest_lang)[1]

    async with Translator() as tr:
        tasks = [
            asyncio.create_task(_one_async(s, dest_code, sem, tr))
            for s in TxtList
        ]
        out = await asyncio.gather(*tasks)

    return list(out), time.perf_counter() - t0


def parse_args() -> Tuple[str, str]:
    default_file = "steve_jobs_variant10.txt"
    default_lang = "Irish"

    if len(sys.argv) == 1:
        return default_file, default_lang

    a1 = sys.argv[1].strip()

    if a1.isdigit():
        variant = int(a1)
        filename = f"steve_jobs_variant{variant}.txt"
        lang = default_lang if len(sys.argv) < 3 else sys.argv[2].strip()
        return filename, lang

    filename = a1
    if not filename.lower().endswith(".txt"):
        filename += ".txt"

    lang = default_lang if len(sys.argv) < 3 else sys.argv[2].strip()
    return filename, lang


async def print_report(
    filename: str, text: str, TxtList: List[str], dest_lang: str
) -> None:
    # 3.5 вивід
    src_name, src_code, src_conf = await LangDetect(text)
    dest_name, dest_code = _dest_name_code(dest_lang)
    conf_str = "N/A" if src_conf is None else f"{src_conf:.6f}"

    print("\nЛР №3 | Асинхронний переклад (googletrans)\n")
    print(f"Файл: {filename}")
    print(f"Кількість символів: {len(text)}")
    print(f"Кількість речень: {len(TxtList)}")
    print(f"Мова оригіналу: {src_name}")
    print(f"Код мови оригіналу: {src_code}")
    print(f"Confidence: {conf_str}")
    print(f"Мова перекладу: {dest_name}")
    print(f"Код мови перекладу: {dest_code}")
    print("\nОригінальний текст:\n")
    print(text)


async def main() -> int:
    # головна функція
    filename, dest_lang = parse_args()

    if not os.path.exists(filename):
        print(f"Файл не знайдено: {filename}")
        print("Приклад запуску:")
        print("python lab3_async_translate.py")
        print("python lab3_async_translate.py 10 Irish")
        print("python lab3_async_translate.py steve_jobs_variant10.txt Irish")
        return 1

    err, text = read_file(filename)
    if err:
        print(err)
        return 1

    TxtList = split_sentences(text)

    await print_report(filename, text, TxtList, dest_lang)

    tr_sync, t_sync = await sync_work(TxtList, dest_lang)
    print("\n--- Переклад синхронно ---\n")
    print(" ".join(tr_sync))
    print(f"\nЧас синхронно: {t_sync:.6f} сек")

    tr_async, t_async = await async_work(TxtList, dest_lang, concurrency=10)
    print("\n--- Переклад асинхронно ---\n")
    print(" ".join(tr_async))
    print(f"\nЧас асинхронно: {t_async:.6f} сек\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))