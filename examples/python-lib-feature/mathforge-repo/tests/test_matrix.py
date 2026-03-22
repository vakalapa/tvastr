"""Tests for the Matrix class — the agent's objective is to make these pass.

These tests exist upfront so the agent has a concrete target.
The agent needs to create the Matrix class that satisfies all of these.
"""

import pytest
from mathforge.matrix import Matrix


class TestMatrixCreation:
    def test_create_from_lists(self):
        m = Matrix([[1, 2], [3, 4]])
        assert m.rows == 2
        assert m.cols == 2

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            Matrix([])

    def test_ragged_raises(self):
        with pytest.raises(ValueError):
            Matrix([[1, 2], [3]])

    def test_single_element(self):
        m = Matrix([[42]])
        assert m.rows == 1
        assert m.cols == 1

    def test_getitem(self):
        m = Matrix([[1, 2], [3, 4]])
        assert m[0][0] == 1
        assert m[1][1] == 4


class TestMatrixAddition:
    def test_add(self):
        a = Matrix([[1, 2], [3, 4]])
        b = Matrix([[5, 6], [7, 8]])
        result = a + b
        assert result[0][0] == 6
        assert result[1][1] == 12

    def test_add_dimension_mismatch(self):
        a = Matrix([[1, 2], [3, 4]])
        b = Matrix([[1, 2, 3], [4, 5, 6]])
        with pytest.raises(ValueError):
            a + b


class TestMatrixMultiplication:
    def test_matmul_square(self):
        a = Matrix([[1, 2], [3, 4]])
        b = Matrix([[5, 6], [7, 8]])
        result = a @ b
        assert result[0][0] == 19
        assert result[0][1] == 22
        assert result[1][0] == 43
        assert result[1][1] == 50

    def test_matmul_rectangular(self):
        a = Matrix([[1, 2, 3], [4, 5, 6]])  # 2x3
        b = Matrix([[7, 8], [9, 10], [11, 12]])  # 3x2
        result = a @ b  # should be 2x2
        assert result.rows == 2
        assert result.cols == 2
        assert result[0][0] == 58
        assert result[1][1] == 154

    def test_matmul_dimension_mismatch(self):
        a = Matrix([[1, 2], [3, 4]])
        b = Matrix([[1, 2], [3, 4], [5, 6]])
        with pytest.raises(ValueError):
            a @ b


class TestMatrixTranspose:
    def test_transpose_square(self):
        m = Matrix([[1, 2], [3, 4]])
        t = m.T
        assert t[0][0] == 1
        assert t[0][1] == 3
        assert t[1][0] == 2
        assert t[1][1] == 4

    def test_transpose_rectangular(self):
        m = Matrix([[1, 2, 3], [4, 5, 6]])  # 2x3
        t = m.T  # should be 3x2
        assert t.rows == 3
        assert t.cols == 2

    def test_double_transpose(self):
        m = Matrix([[1, 2], [3, 4]])
        assert m.T.T[0][0] == m[0][0]
        assert m.T.T[1][1] == m[1][1]


class TestMatrixDeterminant:
    def test_det_1x1(self):
        m = Matrix([[5]])
        assert m.det() == 5

    def test_det_2x2(self):
        m = Matrix([[1, 2], [3, 4]])
        assert m.det() == -2

    def test_det_3x3(self):
        m = Matrix([[1, 2, 3], [4, 5, 6], [7, 8, 0]])
        assert m.det() == 27

    def test_det_identity(self):
        m = Matrix([[1, 0, 0], [0, 1, 0], [0, 0, 1]])
        assert m.det() == 1

    def test_det_non_square_raises(self):
        m = Matrix([[1, 2, 3], [4, 5, 6]])
        with pytest.raises(ValueError):
            m.det()


class TestMatrixRepr:
    def test_repr(self):
        m = Matrix([[1, 2], [3, 4]])
        r = repr(m)
        assert "Matrix" in r
        assert "1" in r and "4" in r
