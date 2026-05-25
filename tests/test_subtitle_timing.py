from src.subtitle_timing import (
    TimedCue,
    TimedWord,
    group_words_into_readable_cues,
    make_heuristic_cues,
    parse_webvtt_cues,
    write_webvtt,
)


def test_groups_native_words_into_readable_phrase_cues() -> None:
    words = [
        TimedWord(text="You", start_time=1.2, end_time=1.4, source="native"),
        TimedWord(text="do", start_time=1.4, end_time=1.55, source="native"),
        TimedWord(text="not", start_time=1.55, end_time=1.75, source="native"),
        TimedWord(text="control", start_time=1.75, end_time=2.1, source="native"),
        TimedWord(text="the", start_time=2.1, end_time=2.25, source="native"),
        TimedWord(text="interruption.", start_time=2.25, end_time=2.9, source="native"),
        TimedWord(text="You", start_time=3.0, end_time=3.2, source="native"),
        TimedWord(text="control", start_time=3.2, end_time=3.55, source="native"),
        TimedWord(text="your", start_time=3.55, end_time=3.75, source="native"),
        TimedWord(text="response.", start_time=3.75, end_time=4.3, source="native"),
    ]

    cues = group_words_into_readable_cues(words, max_words=8, max_duration=3.0)

    assert [cue.text for cue in cues] == [
        "You do not control the interruption.",
        "You control your response.",
    ]
    assert cues[0].start_time == 1.2
    assert cues[0].end_time == 2.9
    assert cues[0].source == "native"
    assert len(cues[0].words) == 6


def test_write_webvtt_formats_cues_with_dot_milliseconds_and_final_newline() -> None:
    cues = [
        TimedCue(start_time=1.2, end_time=3.8, text="You do not control the interruption."),
        TimedCue(start_time=3.9, end_time=6.6, text="You control whether it becomes your day."),
    ]

    assert write_webvtt(cues) == (
        "WEBVTT\n\n"
        "00:00:01.200 --> 00:00:03.800\n"
        "You do not control the interruption.\n\n"
        "00:00:03.900 --> 00:00:06.600\n"
        "You control whether it becomes your day.\n"
    )


def test_make_heuristic_cues_allocates_duration_by_phrase_weight() -> None:
    cues = make_heuristic_cues(
        "You do not control the interruption. You control whether it becomes your day.",
        duration=6.0,
    )

    assert [cue.text for cue in cues] == [
        "You do not control the interruption.",
        "You control whether it becomes your day.",
    ]
    assert cues[0].start_time == 0.0
    assert cues[-1].end_time == 6.0
    assert all(cue.source == "heuristic" for cue in cues)
    assert cues[0].end_time <= cues[1].start_time


def test_parse_webvtt_cues_normalizes_edge_tts_vtt() -> None:
    vtt = (
        "WEBVTT\n\n"
        "00:00:01.200 --> 00:00:03.800\n"
        " You do not control\n"
        " the interruption. \n\n"
        "00:00:03.900 --> 00:00:06.600\n"
        "You control whether it becomes your day.\n"
    )

    cues = parse_webvtt_cues(vtt, source="edge")

    assert cues == [
        TimedCue(
            start_time=1.2,
            end_time=3.8,
            text="You do not control the interruption.",
            source="edge",
        ),
        TimedCue(
            start_time=3.9,
            end_time=6.6,
            text="You control whether it becomes your day.",
            source="edge",
        ),
    ]


def test_parse_webvtt_cues_strips_payload_markup_and_inline_timestamps() -> None:
    vtt = (
        "WEBVTT\n\n"
        "speaker-cue\n"
        "00:00:01.200 --> 00:00:03.800 align:start position:0%\n"
        "<v Narrator><c.emphasis>You control</c> <00:00:02.000>the answer.</v>\n"
    )

    cues = parse_webvtt_cues(vtt, source="edge")

    assert cues == [
        TimedCue(
            start_time=1.2,
            end_time=3.8,
            text="You control the answer.",
            source="edge",
        )
    ]
