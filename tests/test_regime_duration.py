import pandas as pd

from modules import regime_duration as rd


def test_structure():
    r = rd.regime_duration()
    assert isinstance(r, dict)
    assert "available" in r
    if r["available"]:
        assert "durations" in r and "recovery" in r and "band_labels" in r
        assert len(r["band_labels"]) == 5
        assert set(r["durations"].keys()) == set(range(5))


def test_empty_df_degrades():
    r = rd.regime_duration(df=pd.DataFrame())
    assert r["available"] is False


def test_recovery_stat_shape():
    r = rd.regime_duration()
    if not r["available"]:
        return
    rec = r["recovery"]
    assert "n" in rec and "mean" in rec and "median" in rec
    if rec["n"] > 0:
        assert rec["mean"] is not None
        assert rec["median"] is not None
