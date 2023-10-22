"""
Python IDM Helper by zackmark29
Version v1.0.2 | 2021.11.28
"""

from pathlib import Path
from types import ModuleType
from typing import Any, Optional

from comtypes import client  # type: ignore
from comtypes.automation import VT_EMPTY  # type: ignore


def check_folder(*dirs: Path) -> Path:
    for d in dirs:
        if d.exists():
            return d
    raise NotADirectoryError(
        "Looks like you don't have IDM installed in your system"
    )


def get_module() -> ModuleType:
    idm_folder_64bit = Path(
        r"C:\Program Files (x86)\Internet Download Manager"
    )
    idm_folder_32bit = Path(r"C:\Program Files\Internet Download Manager")

    idm_folder = check_folder(idm_folder_64bit, idm_folder_32bit)

    try:
        # Registry path: Computer\HKEY_CLASSES_ROOT\TypeLib\
        # {ECF21EAB-3AA8-4355-82BE-F777990001DD}
        UUID = "{ECF21EAB-3AA8-4355-82BE-F777990001DD}"
        return client.GetModule([UUID, 1, 0])
    except OSError:
        # if uuid is not exist in the registry use tlb module instead
        tlb = idm_folder / "idmantypeinfo.tlb"
        if not tlb.exists():
            raise FileNotFoundError(
                f"{tlb} is not exist. Try to re-install your idm"
            )

        return client.GetModule(tlb)


class IDMHelper:
    """
    flags
        0: Display/Pop-up confirmation before downloading
        1: Download automatically without any confirmations dialogs
        2: Display confirmation if found duplicate and add only to queue
        3: Add only to queue without any confirmation
    """

    def __init__(
        self,
        url: str,
        output_folder: str,
        output_file_name: str,
        flag: int,
        referer: Optional[str] = None,
        cookies: Optional[str] = None,
        post_data: Optional[str] = None,
        user_name: Optional[str] = None,
        password: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        # common
        self.url = url
        self.flag = flag
        self.output_folder = output_folder
        self.output_filename = output_file_name

        # optionals
        self.referer = referer
        self.cookies = cookies
        self.post_data = post_data
        self.user_name = user_name
        self.password = password
        self.user_agent = user_agent

        self.idm_module = get_module()

    def send_link_to_idm(self) -> int:
        """Simple method with limited parameters"""

        idm: Any = client.CreateObject(
            progid="IDMan.CIDMLinkTransmitter",
            interface=self.idm_module.ICIDMLinkTransmitter,
        )

        res: int = idm.SendLinkToIDM(
            bstrUrl=self.url,
            bstrLocalPath=self.output_folder,
            bstrLocalFileName=self.output_filename,
            lFlags=self.flag,
            bstrReferer=None,
            bstrCookies=None,
            bstrData=None,
            bstrUser=None,
            bstrPassword=None,
        )
        return res

    def send_link_to_idm2(self) -> None:
        """Method with all the parameters"""

        idm: Any = client.CreateObject(
            progid="IDMan.CIDMLinkTransmitter",
            interface=self.idm_module.ICIDMLinkTransmitter2,
        )
        idm.SendLinkToIDM2(
            bstrUrl=self.url,
            bstrReferer=self.referer,
            bstrCookies=self.cookies,
            bstrData=self.post_data,
            bstrUser=self.user_name,
            bstrPassword=self.password,
            bstrLocalPath=self.output_folder,
            bstrLocalFileName=self.output_filename,
            lFlags=self.flag,
            reserved1=self.user_agent if self.user_agent else VT_EMPTY,
            reserved2=VT_EMPTY,
        )


if __name__ == "__main__":
    url = "http://www.internetdownloadmanager.com/idman401.exe"

    output_folder = Path.cwd()
    output_filename = "idman.exe"
    user_agent = None
    flag = 3  # see above the flag information
    idm = IDMHelper(url, str(output_folder), output_filename, flag)
    idm.send_link_to_idm()
    # idm.send_link_to_idm2()
