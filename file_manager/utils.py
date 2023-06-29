from collections import Counter
import os
from pathlib import Path
from typing import Tuple, List
import cutie

def folder_chooser(folder: Path):
    assert folder.is_dir()
    choices: List[Tuple[Path, str]] = []
    for root, _, files in os.walk(folder):
        res = dict(Counter([Path(f).suffix for f in files]))
        desc = ' , '.join([f'{k}: {v}' for k, v in res.items()])
        choices.append((Path(root), desc))
    index = cutie.select([f'{p} ({d})' for p, d in choices])
    return choices[index]

if __name__ == '__main__':
    print(folder_chooser(Path('/home/quy/sage')))

