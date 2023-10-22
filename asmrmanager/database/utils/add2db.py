import json
import os

from asmrmanager.database.manage import DataBaseManager


def add2db(start_dir: str):
    db = DataBaseManager()
    for root, dirs, files in os.walk(start_dir):
        for file in files:
            if file.startswith("RJ") and file.endswith(".json"):
                with open(os.path.join(root, file), encoding="utf8") as f:
                    db.add_info(json.load(f))

    db.commit()


if __name__ == "__main__":
    add2db(r"D:\bit_download\asmr")
