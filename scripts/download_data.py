"""Baixa os Parquets do SRAG e o dicionário de dados para data/.

O dataset é um "banco vivo": o nome do arquivo muda a cada atualização
(INFLUDyy-dd-mm-aaaa). Para usar outra versão, passe --date dd-mm-aaaa.
"""
import argparse
import urllib.request
from pathlib import Path

BASE_URL = "https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/SRAG"
DEFAULT_DATE = "16-11-2026"
YEARS = (2025, 2026)
DICTIONARY = "dicionario-de-dados-2019-a-2025.pdf"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def download(url: str, dest: Path) -> None:
    if dest.exists():
        print(f"já existe: {dest.name}")
        return
    print(f"baixando {url}")
    urllib.request.urlretrieve(url, dest)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=DEFAULT_DATE, help="dd-mm-aaaa da versão")
    args = parser.parse_args()

    DATA_DIR.mkdir(exist_ok=True)
    for year in YEARS:
        name = f"INFLUD{year % 100}-{args.date}.parquet"
        download(f"{BASE_URL}/{year}/{name}", DATA_DIR / name)
    download(f"{BASE_URL}/{DICTIONARY}", DATA_DIR / DICTIONARY)


if __name__ == "__main__":
    main()
