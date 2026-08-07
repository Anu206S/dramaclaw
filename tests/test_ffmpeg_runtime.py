"""ffmpeg/ffprobe 可执行文件解析与预检的回归测试。

背景：Windows 本地部署用户在「合成剧集」时只会看到
``[WinError 2] 系统找不到指定的文件。`` —— 这是 ``subprocess.Popen`` 找不到
``ffmpeg.exe`` 时抛的原始错误，对用户零指导价值。同时 ``FFMPEG_PATH`` 虽然在
config 里有定义、也被 ``get_video_config()`` 暴露成配置项，但全仓调用点写死了
``"ffmpeg"`` 字面量，导致这个配置从未生效。
"""

from __future__ import annotations

import os
import shutil
import sys

import pytest

from novelvideo import ffmpeg_runtime


@pytest.fixture(autouse=True)
def _clear_ffmpeg_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """每个用例都从「未配置」的干净状态出发。"""
    monkeypatch.delenv("FFMPEG_PATH", raising=False)
    monkeypatch.delenv("FFPROBE_PATH", raising=False)


class TestExecutableResolution:
    def test_defaults_to_bare_command_names(self) -> None:
        assert ffmpeg_runtime.ffmpeg_executable() == "ffmpeg"
        assert ffmpeg_runtime.ffprobe_executable() == "ffprobe"

    def test_ffmpeg_path_env_is_honoured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FFMPEG_PATH", "/opt/ff/ffmpeg")
        assert ffmpeg_runtime.ffmpeg_executable() == "/opt/ff/ffmpeg"

    def test_blank_ffmpeg_path_falls_back_to_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FFMPEG_PATH", "   ")
        assert ffmpeg_runtime.ffmpeg_executable() == "ffmpeg"

    def test_ffprobe_is_derived_as_sibling_of_ffmpeg_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """官方发行包里 ffmpeg 与 ffprobe 同目录，只配一个变量就够。"""
        monkeypatch.setenv("FFMPEG_PATH", "/opt/ff/ffmpeg")
        assert ffmpeg_runtime.ffprobe_executable() == os.path.join("/opt/ff", "ffprobe")

    def test_ffprobe_derivation_preserves_executable_suffix(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Windows 上是 ffmpeg.exe / ffprobe.exe，后缀不能丢。"""
        monkeypatch.setenv("FFMPEG_PATH", "/opt/ff/ffmpeg.exe")
        assert ffmpeg_runtime.ffprobe_executable() == os.path.join("/opt/ff", "ffprobe.exe")

    def test_explicit_ffprobe_path_wins_over_derivation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FFMPEG_PATH", "/opt/ff/ffmpeg")
        monkeypatch.setenv("FFPROBE_PATH", "/elsewhere/ffprobe")
        assert ffmpeg_runtime.ffprobe_executable() == "/elsewhere/ffprobe"

    def test_resolution_is_lazy_not_import_time(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """模块常量式的解析会让运行期设置的环境变量失效，这里锁住惰性求值。"""
        monkeypatch.setenv("FFMPEG_PATH", "/first/ffmpeg")
        assert ffmpeg_runtime.ffmpeg_executable() == "/first/ffmpeg"
        monkeypatch.setenv("FFMPEG_PATH", "/second/ffmpeg")
        assert ffmpeg_runtime.ffmpeg_executable() == "/second/ffmpeg"


class TestAvailability:
    def test_available_when_which_resolves(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
        assert ffmpeg_runtime.ffmpeg_available() is True
        assert ffmpeg_runtime.ffprobe_available() is True

    def test_unavailable_when_which_returns_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(shutil, "which", lambda _name: None)
        assert ffmpeg_runtime.ffmpeg_available() is False
        assert ffmpeg_runtime.ffprobe_available() is False

    def test_availability_checks_the_configured_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: list[str] = []

        def fake_which(name: str) -> str | None:
            seen.append(name)
            return None

        monkeypatch.setenv("FFMPEG_PATH", "/opt/ff/ffmpeg")
        monkeypatch.setattr(shutil, "which", fake_which)
        ffmpeg_runtime.ffmpeg_available()
        assert seen == ["/opt/ff/ffmpeg"]


class TestEnsureFfmpegReady:
    def test_passes_when_both_binaries_resolve(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
        ffmpeg_runtime.ensure_ffmpeg_ready()

    def test_raises_actionable_error_when_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(shutil, "which", lambda _name: None)
        with pytest.raises(ffmpeg_runtime.FfmpegUnavailableError) as excinfo:
            ffmpeg_runtime.ensure_ffmpeg_ready()

        message = str(excinfo.value)
        # 报错必须自带安装命令、重启提示与 FFMPEG_PATH 出路，
        # 否则用户拿到的信息量不比 [WinError 2] 多。
        assert "ffmpeg" in message
        assert ffmpeg_runtime.install_hint() in message
        assert "重启" in message
        assert "FFMPEG_PATH" in message

    def test_error_is_a_value_error_for_existing_handlers(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(shutil, "which", lambda _name: None)
        with pytest.raises(ValueError):
            ffmpeg_runtime.ensure_ffmpeg_ready()

    def test_can_skip_ffprobe_requirement(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            shutil, "which", lambda name: None if "ffprobe" in name else f"/usr/bin/{name}"
        )
        ffmpeg_runtime.ensure_ffmpeg_ready(require_ffprobe=False)
        with pytest.raises(ffmpeg_runtime.FfmpegUnavailableError):
            ffmpeg_runtime.ensure_ffmpeg_ready()

    def test_missing_binary_name_is_reported(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """配了自定义路径时，报错要指出实际找的是哪个文件。"""
        monkeypatch.setenv("FFMPEG_PATH", "/opt/ff/ffmpeg")
        monkeypatch.setattr(shutil, "which", lambda _name: None)
        with pytest.raises(ffmpeg_runtime.FfmpegUnavailableError) as excinfo:
            ffmpeg_runtime.ensure_ffmpeg_ready(require_ffprobe=False)
        assert "/opt/ff/ffmpeg" in str(excinfo.value)


class TestInstallHint:
    def test_hint_is_platform_specific(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(ffmpeg_runtime.sys, "platform", "win32")
        assert "winget" in ffmpeg_runtime.install_hint()
        monkeypatch.setattr(ffmpeg_runtime.sys, "platform", "darwin")
        assert "brew" in ffmpeg_runtime.install_hint()
        monkeypatch.setattr(ffmpeg_runtime.sys, "platform", "linux")
        assert "apt" in ffmpeg_runtime.install_hint()


class TestSubprocessTranslatesMissingExecutable:
    """裸 FileNotFoundError 的兜底翻译。

    预检只挡得住入口；``_audio_duration`` 这类按需调用的辅助函数没法在入口
    无条件预检（没有音频文件时它压根不碰 ffprobe，预检反而会误伤）。所以真正
    的兜底放在 ``run_project_subprocess`` 这一层，覆盖全部调用点。
    """

    def test_missing_ffmpeg_becomes_actionable_error(self) -> None:
        from novelvideo.task_backend.subprocesses import run_project_subprocess

        with pytest.raises(ffmpeg_runtime.FfmpegUnavailableError) as excinfo:
            run_project_subprocess(["definitely-not-ffmpeg-xyz", "-version"])

        message = str(excinfo.value)
        assert "definitely-not-ffmpeg-xyz" in message

    def test_ffmpeg_named_binary_gets_install_hint(self) -> None:
        from novelvideo.task_backend.subprocesses import run_project_subprocess

        with pytest.raises(ffmpeg_runtime.FfmpegUnavailableError) as excinfo:
            run_project_subprocess(["/nonexistent/dir/ffmpeg", "-version"])

        message = str(excinfo.value)
        assert ffmpeg_runtime.install_hint() in message
        assert "重启" in message

    def test_successful_command_is_unaffected(self) -> None:
        from novelvideo.task_backend.subprocesses import run_project_subprocess

        result = run_project_subprocess(
            [sys.executable, "-c", "print('ok')"], capture_output=True, text=True
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "ok"


class TestNoHardcodedBinaries:
    """防回归守卫：调用点不许再写死可执行文件名。

    这个 bug 的根因就是 ``FFMPEG_PATH`` 有定义、有暴露，却没有任何调用点消费它 ——
    配置项存在但不生效，比没有这个配置更容易把人带沟里。守住这条，
    resolver 才不会重新退化成摆设。
    """

    FORBIDDEN = ('"ffmpeg",', '"ffprobe",', 'shutil.which("ffmpeg")', 'shutil.which("ffprobe")')
    # `queue_kind="ffmpeg"` 是任务通道名，与可执行文件同名纯属巧合。
    # 按语法形状排除而不是整文件豁免 —— 否则同一文件里真正写死的调用点会被放过。
    QUEUE_KIND_SHAPE = 'queue_kind="ffmpeg"'

    def test_no_hardcoded_executable_literals_in_src(self) -> None:
        from pathlib import Path

        import novelvideo

        root = Path(novelvideo.__file__).parent
        offenders: list[str] = []
        for path in sorted(root.rglob("*.py")):
            if path.name == "ffmpeg_runtime.py":
                continue
            text = path.read_text(encoding="utf-8").replace(self.QUEUE_KIND_SHAPE, "")
            for pattern in self.FORBIDDEN:
                if pattern in text:
                    offenders.append(f"{path.relative_to(root)}: {pattern}")

        assert offenders == [], (
            "发现写死的 ffmpeg/ffprobe 调用点，请改用 "
            "novelvideo.ffmpeg_runtime 的 resolver：\n" + "\n".join(offenders)
        )

    def test_queue_kind_names_are_left_alone(self) -> None:
        """通道名与可执行文件同名，别被 resolver 误伤。"""
        from novelvideo.task_backend.queues import QUEUE_KINDS

        assert "ffmpeg" in QUEUE_KINDS


class TestVideoConfigReportsEffectivePath:
    def test_get_video_config_reflects_runtime_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """配置面板展示的值必须是真正会被执行的那个。"""
        from novelvideo import config

        monkeypatch.setenv("FFMPEG_PATH", "/opt/ff/ffmpeg")
        assert config.get_video_config()["ffmpeg_path"] == "/opt/ff/ffmpeg"
