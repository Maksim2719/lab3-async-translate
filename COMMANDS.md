# Команди для ЛР3 (Async Translate)

## 1) Створення і активація venv
python -m venv maksim_chypilka
.\maksim_chypilka\Scripts\activate

## 2) Оновлення pip та встановлення бібліотеки
python -m pip install --upgrade pip
pip install googletrans-py39==4.0.2

## 3) Перевірка версії Python та пакетів
python --version
pip list
pip show googletrans-py39

## 4) Запуск програми
python -m lab3_async_translate
# або з параметрами:
python -m lab3_async_translate steve_jobs_variant10 Irish
python -m lab3_async_translate 10 Irish

## 5) GitHub
git add -A
git commit -m "Final version for Lab3 (variant 10)"
git push
