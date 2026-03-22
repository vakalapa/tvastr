# Objective

Add a `Matrix` class to the `mathforge` library that supports:

1. Creation from a list of lists
2. Matrix addition (`+` operator)
3. Matrix multiplication (`@` operator)
4. Transpose (`.T` property)
5. Determinant calculation for square matrices (`.det()` method)
6. Pretty string representation (`__repr__`)

# Acceptance Criteria

- All existing tests in `tests/` continue to pass (regression)
- New tests in `tests/test_matrix.py` cover all 6 features above
- Matrix operations raise appropriate errors for dimension mismatches
- Determinant works for 1x1, 2x2, 3x3, and NxN matrices

# Constraints

- Pure Python only — no numpy or external dependencies
- Do not modify existing `Vector` class behavior
