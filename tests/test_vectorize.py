import numpy as np

from apainting.vectorize import trace_skeleton


def test_trace_simple_line():
    skel = np.zeros((20, 20), dtype=bool)
    skel[10, 2:18] = True
    paths = trace_skeleton(skel, min_length=2)
    assert paths
    assert max(p.length for p in paths) >= 10
