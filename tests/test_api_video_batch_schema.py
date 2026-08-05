import pytest
from pydantic import ValidationError

from novelvideo.api.schemas import BeatsRegenerateRequest, SingleVideoRequest


def test_single_video_request_allows_nine_item_queue_batch():
    request = SingleVideoRequest(batch_id="video-batch", batch_size=9)

    assert request.batch_size == 9


def test_single_video_request_rejects_more_than_nine_items():
    with pytest.raises(ValidationError):
        SingleVideoRequest(batch_id="video-batch", batch_size=10)


def test_first_frame_batch_limit_remains_three():
    with pytest.raises(ValidationError):
        BeatsRegenerateRequest(beat_indices=[1, 2, 3, 4], batch_size=4)
