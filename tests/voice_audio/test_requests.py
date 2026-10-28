from types import SimpleNamespace as NS

from evergreen.voice_audio.requests import plan_requests


def scene(sid, *speakers):
    return NS(
        id=sid,
        beats=[
            NS(speaker=s, text=f"t{i}", emotion="e") for i, s in enumerate(speakers)
        ],
    )


def keys(reqs):
    return [(r.key, [t.text for t in r.turns]) for r in reqs]


def test_one_or_two_voices_stay_in_a_single_request():
    reqs = plan_requests(
        [scene("a", "narrator"), scene("b", "lola", "narrator", "lola")]
    )
    assert keys(reqs) == [("a", ["t0"]), ("b", ["t0", "t1", "t2"])]
    assert reqs[1].speakers == ["lola", "narrator"]


def test_third_voice_splits_keeping_order():
    reqs = plan_requests([scene("a", "n", "l", "n", "p", "l", "p")])
    assert keys(reqs) == [("a-1", ["t0", "t1", "t2"]), ("a-2", ["t3", "t4", "t5"])]
    assert [r.scene_id for r in reqs] == ["a", "a"]


def test_every_beat_is_used_exactly_once():
    s = scene("x", *"abcabcabc")
    texts = [t.text for r in plan_requests([s]) for t in r.turns]
    assert texts == [b.text for b in s.beats]
