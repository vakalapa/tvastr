"""Tests for tvastr.master.decomposer — checklist extraction and SubObjective dataclass."""

from tvastr.master.decomposer import SubObjective, decompose_from_checklist


class TestDecomposeFromChecklist:
    def test_checklist_extraction(self):
        """Objective with '# Sub-objectives' + checkboxes extracts items."""
        objective = (
            "# Main Objective\n"
            "Do something big.\n\n"
            "# Sub-objectives\n"
            "- [ ] Implement feature A\n"
            "- [x] Implement feature B\n"
            "- [ ] Write tests for feature C\n"
        )
        result = decompose_from_checklist(objective)
        assert result is not None
        assert len(result) == 3
        assert result[0].description == "Implement feature A"
        assert result[1].description == "Implement feature B"
        assert result[2].description == "Write tests for feature C"

    def test_checklist_no_section(self):
        """Objective without checkboxes returns None."""
        objective = (
            "# Main Objective\n"
            "Do something big.\n\n"
            "No checklist here, just prose.\n"
        )
        result = decompose_from_checklist(objective)
        assert result is None

    def test_checklist_empty_objective(self):
        """Empty string returns None."""
        result = decompose_from_checklist("")
        assert result is None

    def test_checklist_priority_ordering(self):
        """Items get sequential priorities starting from 0."""
        objective = (
            "# Sub-objectives\n"
            "- [ ] First task\n"
            "- [ ] Second task\n"
            "- [ ] Third task\n"
        )
        result = decompose_from_checklist(objective)
        assert result is not None
        assert [s.priority for s in result] == [0, 1, 2]


class TestSubObjectiveDataclass:
    def test_sub_objective_dataclass(self):
        """Construct SubObjective and verify all fields."""
        sub = SubObjective(
            description="Add login page",
            acceptance_criteria=["Page renders", "Form submits"],
            priority=1,
            depends_on=[0],
            suggested_files=["src/login.py"],
        )
        assert sub.description == "Add login page"
        assert sub.acceptance_criteria == ["Page renders", "Form submits"]
        assert sub.priority == 1
        assert sub.depends_on == [0]
        assert sub.suggested_files == ["src/login.py"]
