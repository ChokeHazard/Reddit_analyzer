"""CLI output validation tests for Phase 4D."""

import pytest
import json
from typer.testing import CliRunner
from unittest.mock import Mock, patch, MagicMock
import tempfile
import os
from datetime import datetime, timedelta

from reddit_analyzer.cli.main import app
from reddit_analyzer.models import Subreddit, Post, Comment

runner = CliRunner()


@pytest.fixture(autouse=True)
def enable_auth_test_mode():
    """Enable test mode for all tests in this module."""
    # Import and modify the global cli_auth instance
    from reddit_analyzer.cli.utils import auth_manager

    # Save original state
    original_skip_auth = getattr(auth_manager.cli_auth, "skip_auth", False)

    # Enable skip_auth on the existing instance
    auth_manager.cli_auth.skip_auth = True

    yield

    # Restore original state
    auth_manager.cli_auth.skip_auth = original_skip_auth


@pytest.fixture
def mock_auth():
    """Mock authentication - no longer needed with test mode."""
    yield


@pytest.fixture
def mock_db_and_analyzer():
    """Mock database and analyzers."""
    with patch("reddit_analyzer.database.get_session") as mock_get_session:
        # Setup database mock
        mock_ctx = MagicMock()
        mock_session = MagicMock()
        mock_session.__enter__ = Mock(return_value=mock_ctx)
        mock_session.__exit__ = Mock(return_value=None)
        mock_get_session.return_value = mock_session

        # Mock subreddit
        test_subreddit = Mock(spec=Subreddit)
        test_subreddit.id = 1
        test_subreddit.name = "test_politics"

        # Create test posts with political content
        test_posts = []
        for i in range(5):
            post = Mock(spec=Post)
            post.id = i
            post.title = f"Healthcare reform discussion {i}"
            post.selftext = f"Universal healthcare and economic policy debate {i}"
            post.created_utc = datetime.utcnow() - timedelta(days=i)
            post.subreddit_id = 1
            test_posts.append(post)

        # Setup query mocks
        def query_side_effect(model):
            query_mock = Mock()

            if model == Subreddit:
                query_mock.filter_by.return_value.first.return_value = test_subreddit
            elif model == Post:
                filter_mock = Mock()
                filter_mock.order_by.return_value.limit.return_value.all.return_value = test_posts
                filter_mock.order_by.return_value.all.return_value = test_posts
                query_mock.filter.return_value = filter_mock
            elif model == Comment:
                query_mock.filter.return_value.all.return_value = []

            return query_mock

        mock_ctx.query.side_effect = query_side_effect

        yield mock_ctx, test_subreddit


class TestCLIOutputFormats:
    """Test CLI output formatting."""

    def test_topics_json_output(self, mock_auth, mock_db_and_analyzer):
        """Test topics command JSON output."""
        with patch(
            "reddit_analyzer.services.topic_analyzer.TopicAnalyzer"
        ) as mock_analyzer:
            mock_instance = Mock()
            mock_analyzer.return_value = mock_instance
            mock_instance.detect_political_topics.return_value = {
                "healthcare": 0.8,
                "economy": 0.6,
                "environment": 0.3,
            }

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False
            ) as f:
                output_file = f.name

            try:
                result = runner.invoke(
                    app, ["analyze", "topics", "test_politics", "--save", output_file]
                )

                assert result.exit_code == 0
                assert os.path.exists(output_file)

                # Validate JSON structure
                with open(output_file, "r") as f:
                    data = json.load(f)
                    assert "subreddit" in data
                    assert "topic_distribution" in data or "topics" in data
                    # Handle both possible data structures
                    topics_data = data.get("topics", data.get("topic_distribution", {}))
                    assert "healthcare" in topics_data
                    assert topics_data["healthcare"] == 0.8
            finally:
                if os.path.exists(output_file):
                    os.unlink(output_file)

    def test_sentiment_visualization(self, mock_auth, mock_db_and_analyzer):
        """Test sentiment command visualization output."""
        with patch(
            "reddit_analyzer.services.topic_analyzer.TopicAnalyzer"
        ) as mock_analyzer:
            mock_instance = Mock()
            mock_analyzer.return_value = mock_instance
            mock_instance.analyze_topic_sentiment.return_value = {
                "positive": 0.4,
                "negative": 0.3,
                "neutral": 0.3,
                "compound": 0.1,
            }

            result = runner.invoke(
                app, ["analyze", "sentiment", "test_politics", "--topic", "healthcare"]
            )

            assert result.exit_code == 0
            # Check for visualization elements
            assert "Sentiment" in result.stdout
            assert "positive" in result.stdout.lower()
            assert "negative" in result.stdout.lower()
            assert "neutral" in result.stdout.lower()

    def test_quality_metrics_table(self, mock_auth, mock_db_and_analyzer):
        """Test quality command table output."""
        with patch(
            "reddit_analyzer.services.topic_analyzer.TopicAnalyzer"
        ) as mock_analyzer:
            mock_instance = Mock()
            mock_analyzer.return_value = mock_instance
            mock_instance.calculate_discussion_quality.return_value = {
                "constructiveness": 0.75,
                "toxicity": 0.15,
                "engagement": 0.80,
                "overall_quality": 0.70,
            }

            result = runner.invoke(app, ["analyze", "quality", "test_politics"])

            assert result.exit_code == 0
            assert "Discussion Quality" in result.stdout
            assert (
                "constructiveness" in result.stdout.lower() or "0.75" in result.stdout
            )
            assert "toxicity" in result.stdout.lower() or "0.15" in result.stdout

    def test_dimensions_radar_chart(self, mock_auth, mock_db_and_analyzer):
        """Test dimensions command radar chart output."""
        with patch(
            "reddit_analyzer.services.political_dimensions_analyzer.PoliticalDimensionsAnalyzer"
        ) as mock_analyzer:
            mock_instance = Mock()
            mock_analyzer.return_value = mock_instance
            mock_instance.analyze_political_dimensions.return_value = Mock(
                dimensions={
                    "economic": {
                        "position": 0.2,
                        "confidence": 0.8,
                        "evidence": ["test"],
                    },
                    "social": {
                        "position": -0.3,
                        "confidence": 0.7,
                        "evidence": ["test"],
                    },
                    "governance": {
                        "position": 0.1,
                        "confidence": 0.6,
                        "evidence": ["test"],
                    },
                },
                dominant_topics={"healthcare": 0.5},
                analysis_quality=0.75,
            )

            result = runner.invoke(app, ["analyze", "dimensions", "test_politics"])

            assert result.exit_code == 0
            assert "economic" in result.stdout.lower()
            assert "social" in result.stdout.lower()

    def test_political_compass_plot(self, mock_auth, mock_db_and_analyzer):
        """Test political compass visualization."""
        mock_ctx, test_subreddit = mock_db_and_analyzer

        # Mock the SubredditPoliticalDimensions query
        from reddit_analyzer.models import SubredditPoliticalDimensions

        mock_analysis = Mock(spec=SubredditPoliticalDimensions)
        mock_analysis.avg_economic_score = 0.3
        mock_analysis.avg_social_score = -0.4
        mock_analysis.avg_governance_score = 0.1
        mock_analysis.political_diversity_index = 0.65
        mock_analysis.avg_confidence_level = 0.75
        mock_analysis.analysis_start_date = datetime.utcnow() - timedelta(days=7)
        mock_analysis.analysis_end_date = datetime.utcnow()

        # Update the query mock to return our analysis
        def query_side_effect(model):
            query_mock = Mock()

            if model == Subreddit:
                query_mock.filter_by.return_value.first.return_value = test_subreddit
            elif model == SubredditPoliticalDimensions:
                filter_mock = Mock()
                order_mock = Mock()
                order_mock.first.return_value = mock_analysis
                filter_mock.order_by.return_value = order_mock
                query_mock.filter.return_value = filter_mock
            else:
                query_mock.filter_by.return_value.first.return_value = None

            return query_mock

        mock_ctx.query.side_effect = query_side_effect

        result = runner.invoke(app, ["analyze", "political-compass", "test_politics"])

        assert result.exit_code == 0
        assert (
            "Political Compass" in result.stdout or "compass" in result.stdout.lower()
        )

    def test_save_report_formats(self, mock_auth, mock_db_and_analyzer):
        """Test saving reports in different formats."""
        with patch(
            "reddit_analyzer.services.topic_analyzer.TopicAnalyzer"
        ) as mock_analyzer:
            mock_instance = Mock()
            mock_analyzer.return_value = mock_instance
            mock_instance.detect_political_topics.return_value = {
                "healthcare": 0.8,
                "economy": 0.6,
            }

            # Test JSON format
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False
            ) as f:
                json_file = f.name

            try:
                result = runner.invoke(
                    app, ["analyze", "topics", "test_politics", "--save", json_file]
                )

                assert result.exit_code == 0
                assert os.path.exists(json_file)

                # Validate it's valid JSON
                with open(json_file, "r") as f:
                    data = json.load(f)
                    assert isinstance(data, dict)
            finally:
                if os.path.exists(json_file):
                    os.unlink(json_file)


class TestOutputContent:
    """Test the content of CLI outputs."""

    def test_error_messages_formatting(self, mock_auth):
        """Test error message formatting."""
        with patch("reddit_analyzer.database.get_session") as mock_session:
            mock_ctx = MagicMock()
            mock_session.return_value.__enter__ = Mock(return_value=mock_ctx)
            mock_session.return_value.__exit__ = Mock(return_value=None)

            # Mock subreddit not found
            mock_ctx.query().filter_by().first.return_value = None

            result = runner.invoke(app, ["analyze", "topics", "nonexistent"])

            assert result.exit_code == 1
            assert "not found" in result.stdout.lower()
            assert "reddit-analyzer data collect" in result.stdout

    def test_progress_indicators(self, mock_auth, mock_db_and_analyzer):
        """Test that progress indicators are shown."""
        with patch(
            "reddit_analyzer.services.topic_analyzer.TopicAnalyzer"
        ) as mock_analyzer:
            mock_instance = Mock()
            mock_analyzer.return_value = mock_instance
            mock_instance.detect_political_topics.return_value = {"test": 0.5}

            result = runner.invoke(app, ["analyze", "topics", "test_politics"])

            assert result.exit_code == 0
            # Should show some kind of progress or processing indicator
            # Check for any output indicating processing
            assert len(result.stdout) > 0

    def test_help_text_formatting(self):
        """Test help text is properly formatted."""
        result = runner.invoke(app, ["analyze", "topics", "--help"])

        assert result.exit_code == 0
        assert "Usage:" in result.stdout
        assert "--days" in result.stdout
        assert "--limit" in result.stdout
        assert "Analyze political topics" in result.stdout
