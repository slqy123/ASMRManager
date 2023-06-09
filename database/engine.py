from pathlib import Path
_instance = None


def get_engine(path: str|None = None, check_same_thread: bool = False):
    from sqlalchemy import create_engine
    if _instance is not None:
        return _instance

    path_ = (path and Path(path)) or Path(__file__).parent.parent / 'data.db'
    return create_engine(f'sqlite:///{path_}?check_same_thread={check_same_thread}')
