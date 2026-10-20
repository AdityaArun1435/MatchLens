"""Live replay: replay time, incremental detection (no look-ahead, same moments as the batch run) and the WebSocket."""
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from matchlens import config, loader, service
from matchlens.api import app
from matchlens.detect import detect_moments
from matchlens.detect.common import MatchContext, in_period_seconds
from matchlens.detect.substitutions import GROUP_GAP_SECONDS
from matchlens.incremental import IncrementalDetector, canonical_ids
from matchlens.live import ReplayEngine, Timeline

from .recap_fixtures import small_match


def real_ids():
    try:
        return [e["match_id"] for e in loader.load_index()]
    except FileNotFoundError:
        return []


def all_matches():
    return [pytest.param(small_match, id="small")] + [
        pytest.param(lambda i=i: service.get_match(i), id=str(i), marks=pytest.mark.needs_data) for i in (3869685, 7580, 3869321)
    ]


def stream(match):
    """Run the incremental detector over the events; return [(moment, number of events fed, last event fed)]."""
    det = IncrementalDetector(match.meta, canonical_ids(match.moments))
    out = []
    events = sorted(match.events, key=lambda e: e.index)
    for n, e in enumerate(events, start=1):
        out += [(m, n, e) for m in det.feed(e)]
    out += [(m, len(events), events[-1]) for m in det.finish()]
    return out, det


# ---- the final set of moments equals the batch detector's output ----------------------------------------------
@pytest.mark.parametrize("make", all_matches())
def test_streamed_moments_equal_the_batch_detector(make):
    match = make()
    streamed, _ = stream(match)
    by_id = {m.id: m for m, _, _ in streamed}
    assert len(by_id) == len(streamed) == len(match.moments)  # each moment released exactly once
    assert [by_id[m.id].model_dump() for m in match.moments] == [m.model_dump() for m in match.moments]


@pytest.mark.parametrize("make", all_matches())
def test_no_moment_is_released_before_its_last_evidence_event_has_been_streamed(make):
    match = make()
    events = sorted(match.events, key=lambda e: e.index)
    position = {e.id: n for n, e in enumerate(events, start=1)}
    for moment, fed, _ in stream(match)[0]:
        assert all(position[eid] <= fed for eid in moment.evidence), moment.id
        assert fed >= position[next(e.id for e in events if e.index == moment.first_index)], moment.id


@pytest.mark.parametrize("make", all_matches())
def test_moments_that_need_a_window_wait_for_it_to_close(make):
    """Quick responses, substitutions and momentum swings are held back until nothing later can change them."""
    match = make()
    full = MatchContext(match.events, match.meta)
    for moment, fed, last in stream(match)[0]:
        s_now = in_period_seconds(last)
        if moment.type == "quick_response" and last.period in config.IN_PLAY_PERIODS:
            horizon = 60 * max(config.QUICK_RESPONSE_BRACE_MIN, config.QUICK_RESPONSE_REPLY_MIN)
            assert full.play_seconds(last) >= moment.stats["goals"][-1]["play_seconds"] + horizon or fed == len(match.events)
        if moment.type == "substitution_impact" and last.period == moment.period:
            subs = [e for e in match.events if e.id in set(moment.evidence)]
            assert s_now >= max(in_period_seconds(e) for e in subs) + GROUP_GAP_SECONDS
            assert s_now >= min(in_period_seconds(e) for e in subs) + 60 * config.SUB_WINDOW_MIN or last.type == "Half End"
        if moment.type == "momentum_swing" and last.period == moment.period:
            end_step = moment.minute - config.PERIOD_OFFSET_SECONDS[moment.period] // 60 + moment.stats["held_minutes"]
            assert int(s_now // 60) > end_step or last.type == "Half End"


@pytest.mark.parametrize("make", all_matches())
def test_a_released_moment_is_what_the_batch_finds_on_the_events_streamed_so_far(make):
    """The content of a moment never depends on events after its release."""
    match = make()
    events = sorted(match.events, key=lambda e: e.index)
    seen: set[int] = set()
    for moment, fed, _ in stream(match)[0]:
        if fed in seen:
            continue
        seen.add(fed)
        prefix = {(m.type, m.first_index): m for m in detect_moments(events[:fed], match.meta)}
        same = prefix.get((moment.type, moment.first_index))
        assert same is not None and same.model_copy(update={"id": moment.id}) == moment, moment.id


@pytest.mark.needs_data
def test_the_final_has_its_momentum_substitution_and_quick_response_moments_delayed():
    match = service.get_match(3869685)
    by_type = {m.type: (m, fed, last) for m, fed, last in stream(match)[0] if m.type in ("quick_response", "substitution_impact")}
    qr, _, last_qr = by_type["quick_response"]
    assert qr.clock_label == "81'" and last_qr.clock_label.startswith("87'") or int(last_qr.minute) >= 86  # about 5 minutes later
    sub, _, last_sub = by_type["substitution_impact"]
    assert sub.clock_label == "116'" and last_sub.type == "Half End" and last_sub.period == 4  # waits for the period to end


# ---- replay time ---------------------------------------------------------------------------------------------
@pytest.mark.needs_data
def test_replay_time_skips_the_breaks_and_the_period_overlap():
    match = service.get_match(3869685)
    tl = Timeline.from_events(match.events)
    assert tl.duration == pytest.approx(sum(tl.length.values()))
    periods = tl.periods()
    assert [p["period"] for p in periods] == [1, 2, 3, 4, 5]
    assert all(a["end"] == pytest.approx(b["start"]) for a, b in zip(periods, periods[1:]))  # nothing between periods
    assert tl.clock(0)["clock"] == "1'" and tl.clock(tl.t_at_minute(45))["period"] == 2
    assert tl.clock(tl.duration)["clock"] == "Pens"


def test_clock_labels_follow_the_batch_convention():
    match = small_match()
    tl = Timeline.from_events(match.events)
    first = min(match.events, key=lambda e: e.index)
    assert tl.clock(tl.t(first))["clock"] == first.clock_label


# ---- engine ----------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("make", all_matches())
def test_engine_messages_are_ordered_and_end_once_with_the_final_score(make):
    match = make()
    engine = ReplayEngine(match)
    msgs, t = [], 0.0
    while not engine.ended:
        t += 90
        msgs += engine.advance(t)
    assert [m["type"] for m in msgs].count("end") == 1 and msgs[-1]["type"] == "end"
    assert msgs[-1]["score"] == list(match.summary.final_score)
    times = [m["t"] for m in msgs if m["type"] == "tick"]
    assert times == sorted(times)
    assert [m["score"] for m in msgs if m["type"] == "score"][-1] == list(match.summary.final_score)
    assert all(m["moment"]["id"] for m in msgs if m["type"] == "moment")


@pytest.mark.needs_data
def test_seeking_gives_the_same_state_as_streaming_to_that_point():
    match = service.get_match(3869685)
    engine = ReplayEngine(match)
    target = engine.timeline.t_at_minute(95)
    streamed = []
    t = 0.0
    while t < target:
        t = min(t + 60, target)
        streamed += engine.advance(t)
    snap = ReplayEngine(match).seek(target)
    assert [m["moment"]["id"] for m in streamed if m["type"] == "moment"] == [m["moment"]["id"] for m in snap["moments"]]
    assert snap["score"] == engine.detector.score == [2, 2] and snap["clock"] == engine.timeline.clock(target)["clock"]
    back = engine.seek(engine.timeline.t_at_minute(30))  # backwards works too
    assert back["score"] == [1, 0] and [m["moment"]["id"] for m in back["moments"]] == ["m_001"]


# ---- WebSocket ---------------------------------------------------------------------------------------------------
@pytest.mark.needs_data
def test_websocket_streams_a_goal_and_obeys_pause_seek_and_resume():
    client = TestClient(app)
    with client.websocket_connect("/matches/3869685/live?speed=60&start=22") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello" and hello["home"] == "Argentina" and hello["speed"] == 60
        goal = None
        for _ in range(400):
            msg = ws.receive_json()
            if msg["type"] == "moment" and msg["moment"]["type"] == "goal":
                goal = msg
                break
        assert goal and goal["moment"]["id"] == "m_001" and goal["clock"] == "23'"
        ws.send_json({"cmd": "pause"})
        for _ in range(200):
            msg = ws.receive_json()
            if msg["type"] == "state" and msg["paused"]:
                break
        else:
            pytest.fail("no paused state")
        ws.send_json({"cmd": "seek", "minute": 60})
        seen = []
        for _ in range(20):
            seen.append(ws.receive_json())
            if seen[-1]["type"] == "catchup":
                break
        catchup = seen[-1]
        assert catchup["type"] == "catchup" and catchup["score"] == [2, 0] and [m["moment"]["id"] for m in catchup["moments"]] == ["m_001", "m_002"]
        ws.send_json({"cmd": "speed", "value": 30})
        ws.send_json({"cmd": "resume"})
        for _ in range(200):
            msg = ws.receive_json()
            if msg["type"] == "tick":
                assert msg["t"] >= catchup["t"]
                break
        else:
            pytest.fail("no tick after resume")


@pytest.mark.needs_data
def test_websocket_rejects_an_unknown_match():
    with pytest.raises(WebSocketDisconnect):
        with TestClient(app).websocket_connect("/matches/1/live"):
            pass


# ---- commentary captions -----------------------------------------------------------------------------------------
@pytest.mark.needs_data
def test_captions_exist_for_important_moments_only_and_are_deterministic():
    match = service.get_match(3869685)
    engine = ReplayEngine(match)
    msgs, t = [], 0.0
    while not engine.ended:
        t += 120
        msgs += engine.advance(t)
    moments = [m for m in msgs if m["type"] == "moment"]
    for m in moments:
        assert (m["caption"] is not None) == (m["moment"]["importance"] >= 0.6), m["moment"]["id"]
    goal = next(m for m in moments if m["moment"]["id"] == "m_004")
    assert goal["caption"] == "81' Goal! Kylian Mbappé for France to level the score. Argentina 2-2 France."
    ReplayEngine(match)  # building a second engine changes nothing
    assert [m["caption"] for m in moments] == [m["caption"] for m in [x for x in _run(match) if x["type"] == "moment"]]


def _run(match):
    engine, out, t = ReplayEngine(match), [], 0.0
    while not engine.ended:
        t += 120
        out += engine.advance(t)
    return out
