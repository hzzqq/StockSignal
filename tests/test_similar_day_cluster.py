import pandas as pd

from modules import similar_day_cluster as sdc


def test_cluster_structure():
    r = sdc.similar_day_cluster()
    assert isinstance(r, dict)
    assert "available" in r and "similar" in r and "forward_stats" in r
    if r["available"]:
        assert isinstance(r["similar"], list)
        assert set(r["forward_stats"].keys()) >= {5, 10, 20}


def test_empty_df_degrades():
    r = sdc.similar_day_cluster(df=pd.DataFrame())
    assert r["available"] is False
