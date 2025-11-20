"""Test Revision Names functionality."""

import re
from unittest.mock import patch

import pytest

from ingenious.utils.revision_names import (
    ADJECTIVES,
    NOUNS,
    generate_funny_revision_id,
    generate_revision_id,
    normalize_revision_id,
    resolve_user_revision_id,
)


class TestGenerateFunnyRevisionId:
    """Test cases for generate_funny_revision_id function."""

    def test_generate_funny_revision_id_format(self):
        """Test that generated ID follows the correct format."""
        revision_id = generate_funny_revision_id()

        # Should match pattern: adjective-noun-8charhex
        pattern = r"^[a-z]+-[a-z]+-[a-f0-9]{8}$"
        assert re.match(pattern, revision_id), f"ID '{revision_id}' doesn't match expected pattern"

    def test_generate_funny_revision_id_parts(self):
        """Test that generated ID contains valid adjective and noun."""
        revision_id = generate_funny_revision_id()
        parts = revision_id.split("-")

        assert len(parts) == 3, f"Expected 3 parts, got {len(parts)}"
        adjective, noun, uuid_part = parts

        assert adjective in ADJECTIVES, f"'{adjective}' not in ADJECTIVES list"
        assert noun in NOUNS, f"'{noun}' not in NOUNS list"
        assert len(uuid_part) == 8, f"UUID part should be 8 chars, got {len(uuid_part)}"

    def test_generate_funny_revision_id_randomization(self):
        """Test that multiple calls produce different results."""
        ids = [generate_funny_revision_id() for _ in range(10)]

        # With the large word lists and UUID, collisions should be extremely rare
        assert len(set(ids)) == len(ids), "Generated IDs should be unique"

    def test_generate_funny_revision_id_uuid_format(self):
        """Test that UUID portion is valid hexadecimal."""
        revision_id = generate_funny_revision_id()
        uuid_part = revision_id.split("-")[2]

        # Should be valid hexadecimal
        try:
            int(uuid_part, 16)
        except ValueError:
            pytest.fail(f"UUID part '{uuid_part}' is not valid hexadecimal")


class TestNormalizeRevisionId:
    """Test cases for normalize_revision_id function."""

    def test_normalize_revision_id_lowercase(self):
        """Test conversion to lowercase."""
        assert normalize_revision_id("MyProject") == "myproject"
        assert normalize_revision_id("UPPERCASE") == "uppercase"

    def test_normalize_revision_id_underscores_to_hyphens(self):
        """Test replacement of underscores with hyphens."""
        assert normalize_revision_id("my_project") == "my-project"
        assert normalize_revision_id("test_workflow_name") == "test-workflow-name"

    def test_normalize_revision_id_invalid_characters(self):
        """Test removal of invalid characters."""
        assert normalize_revision_id("my@project!") == "myproject"
        assert normalize_revision_id("test#$%workflow") == "testworkflow"
        assert normalize_revision_id("spaces here") == "spaceshere"

    def test_normalize_revision_id_leading_trailing_hyphens(self):
        """Test removal of leading and trailing hyphens."""
        assert normalize_revision_id("-myproject-") == "myproject"
        assert normalize_revision_id("--test--") == "test"

    def test_normalize_revision_id_multiple_hyphens(self):
        """Test collapsing of multiple consecutive hyphens."""
        assert normalize_revision_id("my---project") == "my-project"
        assert normalize_revision_id("test--workflow") == "test-workflow"

    def test_normalize_revision_id_combined_rules(self):
        """Test combination of all normalization rules."""
        assert normalize_revision_id("_My@Project#Name_") == "myprojectname"
        assert normalize_revision_id("--TEST__WORKFLOW!!--") == "test-workflow"

    def test_normalize_revision_id_empty_input(self):
        """Test handling of empty input."""
        with pytest.raises(ValueError, match="Revision ID cannot be empty"):
            normalize_revision_id("")

        with pytest.raises(ValueError, match="Revision ID cannot be empty"):
            normalize_revision_id("   ")

    def test_normalize_revision_id_no_valid_characters(self):
        """Test handling when no valid characters remain."""
        with pytest.raises(ValueError, match="contains no valid characters"):
            normalize_revision_id("@#$%!")

        with pytest.raises(ValueError, match="contains no valid characters"):
            normalize_revision_id("---")

    def test_normalize_revision_id_length_validation_valid(self):
        """Test that valid length IDs are accepted."""
        # Test maximum length (50 characters)
        long_name = "a" * 50
        assert normalize_revision_id(long_name) == long_name

        # Test normal length
        assert normalize_revision_id("myproject") == "myproject"

    def test_normalize_revision_id_length_validation_too_long(self):
        """Test that IDs exceeding maximum length are rejected."""
        # Test 51 characters (too long)
        too_long = "a" * 51
        with pytest.raises(ValueError, match="exceeds maximum length of 50 characters"):
            normalize_revision_id(too_long)

        # Test even longer input
        much_too_long = (
            "my-very-very-very-very-very-very-very-long-project-name-that-exceeds-limits"
        )
        with pytest.raises(ValueError, match="exceeds maximum length of 50 characters"):
            normalize_revision_id(much_too_long)

    def test_normalize_revision_id_length_validation_after_normalization(self):
        """Test that length is checked after normalization, not before."""
        # Input that's long but becomes shorter after normalization
        input_with_invalid_chars = "a" * 60 + "@#$%!" + "b" * 10  # 75 chars total

        with pytest.raises(ValueError, match="exceeds maximum length of 50 characters"):
            normalize_revision_id(input_with_invalid_chars)

    @patch("ingenious.utils.revision_names.logger")
    def test_normalize_revision_id_logging(self, mock_logger):
        """Test that function logs the normalization properly."""
        result = normalize_revision_id("Test_Project")

        mock_logger.debug.assert_called_once()
        call_args = mock_logger.debug.call_args
        assert "Normalized revision ID" in call_args[0][0]
        assert call_args[1]["original_name"] == "Test_Project"
        assert call_args[1]["normalized_id"] == result


class TestResolveUserRevisionId:
    """Test cases for resolve_user_revision_id function."""

    def test_resolve_user_revision_id_no_conflict(self):
        """Test when there's no conflict with existing IDs."""
        existing_ids = ["project1", "project2"]
        result = resolve_user_revision_id("myproject", existing_ids)
        assert result == "myproject"

    def test_resolve_user_revision_id_single_conflict(self):
        """Test resolving single conflict by adding -1."""
        existing_ids = ["myproject", "other-project"]
        result = resolve_user_revision_id("myproject", existing_ids)
        assert result == "myproject-1"

    def test_resolve_user_revision_id_multiple_conflicts(self):
        """Test resolving multiple conflicts by finding next available number."""
        existing_ids = ["myproject", "myproject-1", "myproject-2", "myproject-5"]
        result = resolve_user_revision_id("myproject", existing_ids)
        assert result == "myproject-3"  # Should find first available number (3)

    def test_resolve_user_revision_id_normalization(self):
        """Test that input is normalized before conflict resolution."""
        existing_ids = ["my-project"]
        result = resolve_user_revision_id("My_Project", existing_ids)
        assert result == "my-project-1"

    def test_resolve_user_revision_id_empty_input(self):
        """Test handling of empty input."""
        with pytest.raises(ValueError, match="Revision ID cannot be empty"):
            resolve_user_revision_id("", [])

    def test_resolve_user_revision_id_complex_pattern(self):
        """Test with more complex existing patterns."""
        existing_ids = [
            "workflow-test",
            "workflow-test-1",
            "workflow-test-3",
            "workflow-test-10",
            "workflow-other-1",
        ]
        result = resolve_user_revision_id("workflow-test", existing_ids)
        assert result == "workflow-test-2"  # Should find first available number (2)

    def test_resolve_user_revision_id_pattern_matching(self):
        """Test that only exact pattern matches are considered."""
        existing_ids = [
            "myproject",
            "myproject-1",
            "myproject-test-2",  # Should not match
            "other-myproject-3",  # Should not match
        ]
        result = resolve_user_revision_id("myproject", existing_ids)
        assert result == "myproject-2"  # Only myproject-1 should match

    @patch("ingenious.utils.revision_names.logger")
    def test_resolve_user_revision_id_logging_no_conflict(self, mock_logger):
        """Test logging when no conflict occurs."""
        resolve_user_revision_id("myproject", ["other"])
        # Implementation now logs normalization + availability; ensure expected message present.
        assert mock_logger.debug.call_count >= 1
        messages = [c.args[0] for c in mock_logger.debug.call_args_list]
        assert any("User revision ID available" in m for m in messages), (
            "Expected availability log message not found"
        )
        # Last call should be the availability message.
        assert "User revision ID available" in mock_logger.debug.call_args_list[-1].args[0]

    @patch("ingenious.utils.revision_names.logger")
    def test_resolve_user_revision_id_logging_with_conflict(self, mock_logger):
        """Test logging when conflict resolution occurs."""
        resolve_user_revision_id("myproject", ["myproject"])
        # Implementation now logs normalization + conflict resolution; ensure expected message present.
        assert mock_logger.debug.call_count >= 1
        messages = [c.args[0] for c in mock_logger.debug.call_args_list]
        assert any("Resolved user revision ID conflict" in m for m in messages), (
            "Expected conflict resolution log message not found"
        )
        # Last call should be the conflict resolution message.
        assert "Resolved user revision ID conflict" in mock_logger.debug.call_args_list[-1].args[0]


class TestGenerateRevisionId:
    """Test cases for generate_revision_id function."""

    def test_generate_revision_id_with_user_input(self):
        """Test generation with user-provided revision ID."""
        existing_ids = ["other-project"]
        result = generate_revision_id("myproject", existing_ids)
        assert result == "myproject"

    def test_generate_revision_id_with_user_input_conflict(self):
        """Test generation with user input that has conflicts."""
        existing_ids = ["myproject"]
        result = generate_revision_id("myproject", existing_ids)
        assert result == "myproject-1"

    def test_generate_revision_id_without_user_input(self):
        """Test generation without user input (funny name)."""
        existing_ids = ["some-project"]
        result = generate_revision_id(None, existing_ids)

        # Should be a funny name format
        pattern = r"^[a-z]+-[a-z]+-[a-f0-9]{8}$"
        assert re.match(pattern, result), (
            f"Generated ID '{result}' doesn't match funny name pattern"
        )

    def test_generate_revision_id_empty_string_input(self):
        """Test generation with empty string input (should generate funny name)."""
        existing_ids = ["some-project"]
        result = generate_revision_id("", existing_ids)

        # Should be a funny name format
        pattern = r"^[a-z]+-[a-z]+-[a-f0-9]{8}$"
        assert re.match(pattern, result), (
            f"Generated ID '{result}' doesn't match funny name pattern"
        )

    @patch("ingenious.utils.revision_names.resolve_user_revision_id")
    def test_generate_revision_id_calls_resolve_with_user_input(self, mock_resolve):
        """Test that resolve_user_revision_id is called when user input is provided."""
        mock_resolve.return_value = "resolved-id"
        existing_ids = ["existing"]

        result = generate_revision_id("user-input", existing_ids)

        mock_resolve.assert_called_once_with("user-input", existing_ids)
        assert result == "resolved-id"

    @patch("ingenious.utils.revision_names.generate_funny_revision_id")
    def test_generate_revision_id_calls_funny_without_user_input(self, mock_funny):
        """Test that generate_funny_revision_id is called without user input."""
        mock_funny.return_value = "funny-name-12345678"
        existing_ids = ["existing"]

        result = generate_revision_id(None, existing_ids)

        mock_funny.assert_called_once()
        assert result == "funny-name-12345678"

    def test_generate_revision_id_integration(self):
        """Test full integration of the function."""
        existing_ids = ["project1", "project2"]

        # Test with user input
        user_result = generate_revision_id("myproject", existing_ids)
        assert user_result == "myproject"

        # Test without user input
        funny_result = generate_revision_id(None, existing_ids)
        pattern = r"^[a-z]+-[a-z]+-[a-f0-9]{8}$"
        assert re.match(pattern, funny_result)


class TestWordLists:
    """Test cases for the word lists used in funny name generation."""

    def test_adjectives_list_not_empty(self):
        """Test that ADJECTIVES list is not empty."""
        assert len(ADJECTIVES) > 0, "ADJECTIVES list should not be empty"

    def test_nouns_list_not_empty(self):
        """Test that NOUNS list is not empty."""
        assert len(NOUNS) > 0, "NOUNS list should not be empty"

    def test_adjectives_are_lowercase(self):
        """Test that all adjectives are lowercase."""
        for adjective in ADJECTIVES:
            assert adjective.islower(), f"Adjective '{adjective}' should be lowercase"

    def test_nouns_are_lowercase(self):
        """Test that all nouns are lowercase."""
        for noun in NOUNS:
            assert noun.islower(), f"Noun '{noun}' should be lowercase"

    def test_adjectives_no_special_characters(self):
        """Test that adjectives contain only letters."""
        for adjective in ADJECTIVES:
            assert adjective.isalpha(), f"Adjective '{adjective}' should contain only letters"

    def test_nouns_no_special_characters(self):
        """Test that nouns contain only letters."""
        for noun in NOUNS:
            assert noun.isalpha(), f"Noun '{noun}' should contain only letters"

    def test_word_lists_sufficient_diversity(self):
        """Test that word lists have sufficient diversity for uniqueness."""
        # With at least 10 adjectives and 10 nouns, plus 8-char UUID,
        # collisions should be extremely rare
        assert len(ADJECTIVES) >= 10, "Should have at least 10 adjectives for diversity"
        assert len(NOUNS) >= 10, "Should have at least 10 nouns for diversity"
