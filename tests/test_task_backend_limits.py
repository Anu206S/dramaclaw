from novelvideo.task_backend import limits


def test_default_video_limits_allow_nine_queued_per_user_with_three_running(monkeypatch):
    for name in (
        "ST_PROJECT_MAX_ACTIVE_VIDEO_TASKS",
        "ST_PROJECT_USER_MAX_ACTIVE_VIDEO_TASKS",
        "ST_CE_GLOBAL_MAX_ACTIVE_VIDEO_TASKS",
    ):
        monkeypatch.delenv(name, raising=False)

    assert limits.project_lane_active_limit("video") == 12
    assert limits.project_user_lane_active_limit("video") == 9
    assert limits.project_lane_effective_active_limit("video", eligible_user_count=1) == 9
    assert limits.global_lane_concurrency("video") == 3


def test_default_image_limits_allow_nine_queued_per_user_with_three_running(monkeypatch):
    for name in (
        "ST_PROJECT_MAX_ACTIVE_IMAGE_TASKS",
        "ST_PROJECT_USER_MAX_ACTIVE_IMAGE_TASKS",
        "ST_CE_GLOBAL_MAX_ACTIVE_IMAGE_TASKS",
    ):
        monkeypatch.delenv(name, raising=False)

    assert limits.project_lane_active_limit("image") == 12
    assert limits.project_user_lane_active_limit("image") == 9
    assert limits.project_lane_effective_active_limit("image", eligible_user_count=1) == 9
    assert limits.global_lane_concurrency("image") == 3
