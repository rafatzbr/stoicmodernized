"""Regression tests for full-pipeline stage ordering."""

import inspect

import src.main as main


def test_full_pipeline_retimes_subtitles_before_generating_images() -> None:
    """Images must use the scene plan after subtitle/VTT retiming.

    The subtitle stage mutates scenes.json with timings derived from the real
    narration audio. If images are generated first, the final render can show
    visual scenes against a different narration window than the prompt they were
    produced for.
    """

    source = inspect.getsource(main.run)
    subtitles_call = "subtitles(job_id=job_id, mock=media_stage_mock)"
    images_call = "images(\n            job_id=job_id,"

    assert subtitles_call in source
    assert images_call in source
    assert source.index(subtitles_call) < source.index(images_call)
