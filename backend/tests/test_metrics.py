"""T12: h-index on [10, 8, 5, 4, 3] == 4."""
from app.services.metrics import h_index, i10_index


def test_t12_h_index():
    assert h_index([10, 8, 5, 4, 3]) == 4


def test_t12_h_index_edges():
    assert h_index([]) == 0
    assert h_index([1, 1, 1]) == 1
    assert h_index([25, 8, 5, 3, 3]) == 3
    assert i10_index([10, 8, 5, 4, 3]) == 1
