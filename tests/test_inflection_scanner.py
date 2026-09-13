import pandas as pd

from modules import inflection_scanner as ins


def test_events_structure():
    r = ins.list_events()
    assert isinstance(r, dict)
    assert "available" in r and "events" in r
    if r["available"]:
        for e in r["events"]:
            assert {"dim", "date", "type", "extreme", "current"} <= set(e.keys())


def test_series_for_structure():
    r = ins.series_for("red_ratio")
    assert isinstance(r, dict)
    assert "available" in r and "dates" in r and "z" in r


def test_empty_df_degrades():
    r = ins.list_events(df=pd.DataFrame())
    assert r["available"] is False
    r2 = ins.series_for("red_ratio", df=pd.DataFrame())
    assert r2["available"] is False
