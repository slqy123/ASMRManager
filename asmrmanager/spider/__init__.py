from .utils.concurrency import concurrent_rate_limit
from asmrmanager.config import config

# patch concurrent_rate_limit
concurrent_rate_limit.__defaults__ = (
    config.api_max_concurrent_requests,
    config.api_max_requests_per_second,
)

from .downloader import ASMRAPI
from .interface import ASMRDownloadManager, ASMRTagManager, ASMRGeneralManager

__all__ = [
    "ASMRAPI",
    "ASMRDownloadManager",
    "ASMRTagManager",
    "ASMRGeneralManager",
]
