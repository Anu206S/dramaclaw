"""ffmpeg / ffprobe 可执行文件的解析与可用性预检。

ffmpeg 与 ffprobe 是**系统依赖**，CE 不分发其二进制（见
``docs/adr/0002-ffmpeg-system-dependency.md``）。Docker 镜像在构建时装好，
本地部署则要求用户自行安装。

本模块是全仓唯一决定「到底调哪个 ffmpeg」的地方，有两条约束：

1. 调用点不要再写死 ``"ffmpeg"`` / ``"ffprobe"`` 字面量。写死会让 ``FFMPEG_PATH``
   这个对外暴露的配置项形同虚设 —— 用户设了却不生效，比没有这个配置更糟。
   注意：``task_backend/limits.py`` 与 ``queues.py`` 里的 ``"ffmpeg"`` 是**任务通道名**
   而非可执行文件，不在此列。
2. 进入依赖 ffmpeg 的长流程前先调 :func:`ensure_ffmpeg_ready`。否则
   ``subprocess.Popen`` 会在 Windows 上抛出裸的
   ``[WinError 2] 系统找不到指定的文件。``（POSIX 上是
   ``[Errno 2] No such file or directory``），这句话既不说缺的是什么、
   也不说该怎么办，用户根本无从下手。
"""

from __future__ import annotations

import os
import shutil
import sys

__all__ = [
    "FfmpegUnavailableError",
    "ensure_ffmpeg_ready",
    "ffmpeg_available",
    "ffmpeg_executable",
    "ffprobe_available",
    "ffprobe_executable",
    "install_hint",
    "missing_executable_error",
]


class FfmpegUnavailableError(ValueError):
    """ffmpeg / ffprobe 不可用。

    继承 ``ValueError`` 是为了兼容既有调用方 —— 媒体路径上已有多处
    ``except ValueError`` 把失败折叠成任务级错误，换成全新的异常基类会让
    这些地方漏接，反而把可读的提示变回堆栈。
    """


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def ffmpeg_executable() -> str:
    """返回应当执行的 ffmpeg。

    每次调用都重新读环境变量：模块常量式的解析会在 import 时定格，
    运行期（含测试与热加载）再改 ``FFMPEG_PATH`` 就不生效了。
    """
    return _env("FFMPEG_PATH") or "ffmpeg"


def ffprobe_executable() -> str:
    """返回应当执行的 ffprobe。

    未显式配置 ``FFPROBE_PATH`` 时，按同目录兄弟文件从 ``FFMPEG_PATH`` 推导：
    官方发行包（Windows 的 Gyan build、Homebrew、apt）都把两个二进制装在一起，
    强迫用户配两遍纯属多余，且极易只配一个导致半截失败。
    """
    explicit = _env("FFPROBE_PATH")
    if explicit:
        return explicit

    ffmpeg = ffmpeg_executable()
    directory, name = os.path.split(ffmpeg)
    # 用 replace 而不是硬拼字符串，是为了保住 Windows 的 .exe 后缀。
    probe_name = name.replace("ffmpeg", "ffprobe", 1) if "ffmpeg" in name else "ffprobe"
    return os.path.join(directory, probe_name) if directory else probe_name


def _resolvable(executable: str) -> bool:
    # shutil.which 同时覆盖两种形态：裸命令名走 PATH 查找，带目录分量的路径直接校验，
    # 并且在 Windows 上会按 PATHEXT 补 .exe。
    return shutil.which(executable) is not None


def ffmpeg_available() -> bool:
    return _resolvable(ffmpeg_executable())


def ffprobe_available() -> bool:
    return _resolvable(ffprobe_executable())


def install_hint() -> str:
    """返回当前平台的安装命令。"""
    if sys.platform.startswith("win"):
        return "winget install Gyan.FFmpeg"
    if sys.platform == "darwin":
        return "brew install ffmpeg"
    return "sudo apt install ffmpeg"


def _remedy() -> str:
    """安装 ffmpeg 的处置建议。

    刻意把三件事都写进去：装什么、**装完要重启后端**、以及不想改系统 PATH 时的
    出路。前两点是本地部署用户实际卡住的地方 —— 只说「请安装 ffmpeg」的话，
    装完不重启会继续报一模一样的错，看起来就像没修好。
    """
    return (
        f"ffmpeg/ffprobe 是系统依赖，需自行安装：{install_hint()}。"
        "装完请重启后端进程 —— PATH 变更不会传播到已经在运行的进程，"
        "不重启会继续报同样的错。"
        "若已安装但不方便改系统 PATH，可将 FFMPEG_PATH 指向 ffmpeg 可执行文件"
        "（ffprobe 默认按同目录推导，也可用 FFPROBE_PATH 单独指定）。"
    )


def ensure_ffmpeg_ready(*, require_ffprobe: bool = True) -> None:
    """确认 ffmpeg（可选 ffprobe）可用，否则抛出可照做的错误。

    Raises:
        FfmpegUnavailableError: 附带缺失的可执行文件名、平台安装命令、
            重启后端的提醒，以及 ``FFMPEG_PATH`` 这条不改系统 PATH 的出路。
    """
    missing: list[str] = []
    if not ffmpeg_available():
        missing.append(ffmpeg_executable())
    if require_ffprobe and not ffprobe_available():
        missing.append(ffprobe_executable())
    if not missing:
        return

    raise FfmpegUnavailableError(f"未找到可执行的 {' 和 '.join(missing)}。{_remedy()}")


def _looks_like_ffmpeg(executable: str) -> bool:
    name = os.path.basename(executable).lower()
    return "ffmpeg" in name or "ffprobe" in name


def missing_executable_error(executable: str) -> FfmpegUnavailableError:
    """把 ``Popen`` 的 ``FileNotFoundError`` 翻成能照做的提示。

    只有入口预检是不够的：像 ``_audio_duration`` 这种「有音频文件才调 ffprobe」
    的辅助函数没法在入口无条件预检（会误伤本来就不需要音轨的任务），所以真正
    的兜底必须落在实际启动子进程的那一层。
    """
    if _looks_like_ffmpeg(executable):
        return FfmpegUnavailableError(f"未找到可执行的 {executable}。{_remedy()}")
    return FfmpegUnavailableError(
        f"未找到可执行文件 {executable}，请确认它已安装且在 PATH 中"
        "（安装后需重启后端进程才会生效）。"
    )
