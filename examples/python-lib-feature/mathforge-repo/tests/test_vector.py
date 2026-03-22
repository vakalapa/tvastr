"""Existing tests for the Vector class. These must continue to pass (regression)."""

import pytest
from mathforge.vector import Vector


class TestVectorCreation:
    def test_create(self):
        v = Vector(1, 2, 3)
        assert v.dimension == 3

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            Vector()

    def test_components_are_floats(self):
        v = Vector(1, 2, 3)
        assert all(isinstance(c, float) for c in v)


class TestVectorArithmetic:
    def test_add(self):
        a = Vector(1, 2, 3)
        b = Vector(4, 5, 6)
        assert a + b == Vector(5, 7, 9)

    def test_add_dimension_mismatch(self):
        with pytest.raises(ValueError):
            Vector(1, 2) + Vector(1, 2, 3)

    def test_sub(self):
        a = Vector(4, 5, 6)
        b = Vector(1, 2, 3)
        assert a - b == Vector(3, 3, 3)

    def test_scalar_mul(self):
        v = Vector(1, 2, 3)
        assert v * 2 == Vector(2, 4, 6)
        assert 2 * v == Vector(2, 4, 6)

    def test_dot(self):
        a = Vector(1, 2, 3)
        b = Vector(4, 5, 6)
        assert a.dot(b) == 32.0


class TestVectorProperties:
    def test_magnitude(self):
        v = Vector(3, 4)
        assert abs(v.magnitude() - 5.0) < 1e-10

    def test_normalize(self):
        v = Vector(3, 4)
        n = v.normalize()
        assert abs(n.magnitude() - 1.0) < 1e-10

    def test_normalize_zero_raises(self):
        with pytest.raises(ValueError):
            Vector(0, 0, 0).normalize()

    def test_repr(self):
        v = Vector(1, 2, 3)
        assert repr(v) == "Vector(1.0, 2.0, 3.0)"

    def test_equality(self):
        assert Vector(1, 2) == Vector(1, 2)
        assert Vector(1, 2) != Vector(1, 3)

    def test_indexing(self):
        v = Vector(10, 20, 30)
        assert v[0] == 10.0
        assert v[2] == 30.0

    def test_len(self):
        assert len(Vector(1, 2, 3)) == 3
