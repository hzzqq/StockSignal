import pandas as pd

from modules import speculative_clock as sc


def test_series_structure():
    r = sc.speculative_sentiment_series(window=120)
    assert isinstance(r, dict)
    assert "available" in r and "series" in r and "dates" in r
    assert set(r["series"].keys()) <= set(sc._COLS.keys())


def test_phase_structure():
    c = sc.current_phase()
    assert isinstance(c, dict)
    assert "available" in c


def test_empty_df_degrades():
    r = sc.speculative_sentiment_series(df=pd.DataFrame())
    assert r["available"] is False
    c = sc.current_phase(df=pd.DataFrame())
    assert c["available"] is False
