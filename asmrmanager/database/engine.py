from asmrmanager.cli.core import fm

_instance = None


def get_engine(check_same_thread: bool = False):
    from sqlalchemy import create_engine

    if _instance is not None:
        return _instance

    db_path = fm.DATA_PATH / "data.db"
    return create_engine(
        f"sqlite:///{db_path}?check_same_thread={check_same_thread}"
    )
