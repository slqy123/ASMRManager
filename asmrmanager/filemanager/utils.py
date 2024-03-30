import os
from collections import Counter
from pathlib import Path
from typing import Callable, List, Tuple

from asmrmanager.common.select import select, select_multiple


def folder_chooser(
    folder: Path, path_filter: Callable[[Path, dict], bool] = lambda *_: True
) -> Path:
    assert folder.is_dir()
    choices: List[Tuple[Path, str]] = []
    for root, _, files in os.walk(folder):
        if len(files) == 0:
            continue
        res = dict(Counter([Path(f).suffix for f in files]))
        desc = " , ".join([f"{k}: {v}" for k, v in res.items()])
        if path_filter(Path(root), res):
            choices.append((Path(root), desc))
    if len(choices) == 0:
        raise ValueError("No valid path found!")
    index = select([f"{p} ({d})" for p, d in choices])
    return choices[index][0]


def folder_chooser_multiple(
    folder: Path, path_filter: Callable[[Path, dict], bool] = lambda *_: True
) -> List[Path]:
    assert folder.is_dir()
    choices: List[Tuple[Path, str]] = []
    for root, _, files in os.walk(folder):
        if len(files) == 0:
            continue
        res = dict(Counter([Path(f).suffix for f in files]))
        desc = " , ".join([f"{k}: {v}" for k, v in res.items()])
        if path_filter(Path(root), res):
            choices.append((Path(root), desc))
    if len(choices) == 0:
        raise ValueError("No valid path found!")
    indexes = select_multiple([f"{p} ({d})" for p, d in choices])
    return [choices[i][0] for i in indexes]


if __name__ == "__main__":
    print(folder_chooser(Path("/home/quy/sage")))
