# FCONTROL TCI Data Engine

Bu repo FCONTROL TCI indeks ma'lumotlarini avtomatik yangilaydi.

## Fayllar

- `tci_bot.py` — UZSE sahifalaridan ma'lumotlarni o'qiydi
- `tci_config.json` — TCI savati va manbalar
- `.github/workflows/tci.yml` — avtomatik ishga tushirish
- `public/tci_latest.json` — sayt o'qiydigan oxirgi JSON
- `data/raw_uzse_latest.csv` — tekshiruv uchun CSV

## Ishlatish

GitHub Actions ichida `FCONTROL TCI Engine` workflow'ni oching va `Run workflow` bosing.
