from types import ModuleType
from comtypes import client   # type: ignore
from pathlib import Path


def check_folder(*dirs: Path) -> Path:
    for d in dirs:
        if d.exists():
            return d
    raise NotADirectoryError(
        "Looks like you don't have IDM installed in your system"
    )


def get_module() -> ModuleType:
    idm_folder_64bit = Path(
        r'C:\Program Files (x86)\Internet Download Manager'
    )
    idm_folder_32bit = Path(r'C:\Program Files\Internet Download Manager')

    idm_folder = check_folder(idm_folder_64bit, idm_folder_32bit)

    try:
        # Registry path: Computer\HKEY_CLASSES_ROOT\TypeLib\
        # {ECF21EAB-3AA8-4355-82BE-F777990001DD}
        UUID = '{ECF21EAB-3AA8-4355-82BE-F777990001DD}'
        return client.GetModule([UUID, 1, 0])
    except OSError:
        # if uuid is not exist in the registry use tlb module instead
        tlb = idm_folder / 'idmantypeinfo.tlb'
        if not tlb.exists():
            raise FileNotFoundError(
                f'{tlb} is not exist. Try to re-install your idm'
            )

        return client.GetModule(tlb)
