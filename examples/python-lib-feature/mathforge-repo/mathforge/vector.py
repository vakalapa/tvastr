"""A simple Vector class — the existing code the agent must not break."""


class Vector:
    def __init__(self, *components: float):
        if not components:
            raise ValueError("Vector must have at least one component")
        self._components = tuple(float(c) for c in components)

    @property
    def dimension(self) -> int:
        return len(self._components)

    def __getitem__(self, index: int) -> float:
        return self._components[index]

    def __len__(self) -> int:
        return len(self._components)

    def __iter__(self):
        return iter(self._components)

    def __add__(self, other: "Vector") -> "Vector":
        if self.dimension != other.dimension:
            raise ValueError(f"Dimension mismatch: {self.dimension} vs {other.dimension}")
        return Vector(*(a + b for a, b in zip(self, other)))

    def __sub__(self, other: "Vector") -> "Vector":
        if self.dimension != other.dimension:
            raise ValueError(f"Dimension mismatch: {self.dimension} vs {other.dimension}")
        return Vector(*(a - b for a, b in zip(self, other)))

    def __mul__(self, scalar: float) -> "Vector":
        return Vector(*(c * scalar for c in self))

    def __rmul__(self, scalar: float) -> "Vector":
        return self.__mul__(scalar)

    def dot(self, other: "Vector") -> float:
        if self.dimension != other.dimension:
            raise ValueError(f"Dimension mismatch: {self.dimension} vs {other.dimension}")
        return sum(a * b for a, b in zip(self, other))

    def magnitude(self) -> float:
        return sum(c**2 for c in self) ** 0.5

    def normalize(self) -> "Vector":
        mag = self.magnitude()
        if mag == 0:
            raise ValueError("Cannot normalize zero vector")
        return self * (1.0 / mag)

    def __repr__(self) -> str:
        return f"Vector({', '.join(str(c) for c in self._components)})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Vector):
            return NotImplemented
        return self._components == other._components
