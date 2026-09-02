# SPDX-License-Identifier: Elastic-2.0
# Copyright (c) 2026 ClaymoreLab
"""后端进度/日志文案的 i18n 载荷。

后端仍然写中文（当兜底），同时把 i18n code/params 带出来，前端按
`t(code, {defaultValue: text})` 渲染。这里钉住载荷形状和那条最容易踩的
「纯字符串必须清掉上一条 code」的规则。
"""

from novelvideo.i18n_message import (
    lmsg,
    log_entry_payload,
    message_payload,
    message_text,
)
from novelvideo.task_state import TaskState, TaskStateManager


def _manager() -> TaskStateManager:
    # _apply_progress_message 只碰传进来的 state，不需要真的建库。
    return TaskStateManager.__new__(TaskStateManager)


def _state() -> TaskState:
    return TaskState(task_id="t1", task_type="ingest_fast")


def test_localizable_message_carries_code_and_params():
    msg = lmsg("tasks.log.ingest.readingFile", "读取文件: /a.docx", path="/a.docx")
    assert message_text(msg) == "读取文件: /a.docx"
    assert message_payload(msg) == {
        "code": "tasks.log.ingest.readingFile",
        "params": {"path": "/a.docx"},
    }
    # 直接当字符串用（f-string、日志拼接）也还是那句中文。
    assert f"{msg}" == "读取文件: /a.docx"


def test_plain_string_has_no_payload():
    assert message_text("任务已开始") == "任务已开始"
    assert message_payload("任务已开始") is None
    assert log_entry_payload("任务已开始") == "任务已开始"


def test_progress_update_persists_text_and_code():
    state = _state()
    msg = lmsg("tasks.progress.ingest.reading", "读取并校验原文...")
    _manager()._apply_progress_message(state, msg, [msg])

    # 中文照旧落在原列里，老客户端不受影响。
    assert state.current_task == "读取并校验原文..."
    assert state.metadata["current_task_message"] == {
        "code": "tasks.progress.ingest.reading"
    }
    assert state.logs == [
        {"text": "读取并校验原文...", "code": "tasks.progress.ingest.reading"}
    ]


def test_plain_string_update_clears_the_previous_code():
    """这是最容易错的一条：不清就会拿旧 code 去翻新中文。"""
    state = _state()
    _manager()._apply_progress_message(
        state, lmsg("tasks.progress.ingest.reading", "读取并校验原文..."), None
    )
    # 下一次更新来自还没迁移的调用点，只有中文。
    _manager()._apply_progress_message(state, "任务已开始", None)

    assert state.current_task == "任务已开始"
    assert state.metadata["current_task_message"] is None


def test_merge_logs_dedupes_overlapping_tails_across_mixed_shapes():
    state = _state()
    msg = lmsg("tasks.log.ingest.sourceSaved", "原文已保存")
    _manager()._apply_progress_message(state, None, [msg, "任务已开始"])
    # worker 重发了尾部那一段，加一条新的。
    _manager()._apply_progress_message(state, None, ["任务已开始", "任务已完成"])

    assert state.logs == [
        {"text": "原文已保存", "code": "tasks.log.ingest.sourceSaved"},
        "任务已开始",
        "任务已完成",
    ]
