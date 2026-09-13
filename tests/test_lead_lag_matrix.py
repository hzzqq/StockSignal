import pandas as pd

from modules import lead_lag_matrix as ll


def test_matrix_structure():
    r = ll.lead_lag_matrix()
    assert isinstance(r, dict)
    assert "available" in r and "matrix" in r and "dims" in r
    if r["available"]:
        n = len(r["dims"])
        assert len(r["matrix"]) == n
        assert all(len(row) == n for row in r["matrix"])


def test_empty_df_degrades():
    r = ll.lead_lag_matrix(df=pd.DataFrame())
    assert r["available"] is False
