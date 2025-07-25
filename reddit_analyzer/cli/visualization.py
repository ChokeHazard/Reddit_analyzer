"""Visualization CLI commands."""

import typer
from rich.console import Console
from typing import Optional
from datetime import datetime, timedelta

from reddit_analyzer.cli.utils.auth_manager import cli_auth
from reddit_analyzer.cli.utils.ascii_charts import ASCIIVisualizer
from reddit_analyzer.models.post import Post
from reddit_analyzer.models.subreddit import Subreddit
from reddit_analyzer.models.text_analysis import TextAnalysis
from reddit_analyzer.database import get_db
from sqlalchemy import func

viz_app = typer.Typer(help="Visualization commands")
console = Console()
visualizer = ASCIIVisualizer()


@viz_app.command("trends")
@cli_auth.require_auth()
def show_trends(
    subreddit: str = typer.Option(..., help="Specific subreddit (without r/)"),
    days: int = typer.Option(7, help="Number of days to analyze"),
    export: Optional[str] = typer.Option(None, help="Export chart to PNG file"),
):
    """Display trending topics and sentiment."""
    try:
        db = next(get_db())

        # Calculate date range
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)

        # Base query
        query = db.query(Post).filter(Post.created_at >= start_date)

        if subreddit:
            subreddit_obj = (
                db.query(Subreddit)
                .filter(func.lower(Subreddit.name) == subreddit.lower())
                .first()
            )
            if not subreddit_obj:
                console.print(f"❌ Subreddit r/{subreddit} not found", style="red")
                raise typer.Exit(1)
            query = query.filter(Post.subreddit_id == subreddit_obj.id)
            title_prefix = f"r/{subreddit}"
        else:
            title_prefix = "All Subreddits"

        # Get trending data
        posts = query.order_by(Post.score.desc()).limit(100).all()

        if not posts:
            console.print(
                "📭 No posts found for the specified criteria", style="yellow"
            )
            return

        # Analyze trends by day
        daily_counts = {}
        daily_scores = {}

        for post in posts:
            day = post.created_at.strftime("%Y-%m-%d")
            daily_counts[day] = daily_counts.get(day, 0) + 1
            daily_scores[day] = daily_scores.get(day, [])
            daily_scores[day].append(post.score)

        # Calculate average scores per day
        daily_avg_scores = {
            day: sum(scores) / len(scores) if scores else 0
            for day, scores in daily_scores.items()
        }

        # Display post count trends
        console.print(f"🔥 Trending Posts - {title_prefix} (Last {days} days)")
        count_chart = visualizer.horizontal_bar_chart(
            daily_counts, f"Posts per Day - {title_prefix}"
        )
        console.print(count_chart)

        # Display score trends
        if daily_avg_scores:
            score_chart = visualizer.trend_line_chart(
                list(daily_avg_scores.keys()),
                list(daily_avg_scores.values()),
                f"Average Post Score Trend - {title_prefix}",
            )
            console.print(score_chart)

        # Show top posts
        top_posts = sorted(posts, key=lambda p: p.score, reverse=True)[:5]

        from rich.table import Table

        top_table = Table(title=f"🏆 Top Posts - {title_prefix}")
        top_table.add_column("Title", style="cyan", max_width=50)
        top_table.add_column("Score", style="green")
        top_table.add_column("Comments", style="yellow")

        for post in top_posts:
            title = post.title[:47] + "..." if len(post.title) > 50 else post.title
            top_table.add_row(title, str(post.score), str(post.num_comments))

        console.print(top_table)

        # Export if requested
        if export:
            visualizer.export_chart(
                daily_counts, "bar", export, f"Post Trends - {title_prefix}"
            )

    except Exception as e:
        console.print(f"❌ Error generating trends: {e}", style="red")
        raise typer.Exit(1)
    finally:
        db.close()


@viz_app.command("sentiment")
@cli_auth.require_auth()
def show_sentiment(
    subreddit: str = typer.Argument(..., help="Subreddit name (without r/)"),
    export: Optional[str] = typer.Option(None, help="Export chart to PNG file"),
):
    """Show sentiment analysis visualization."""
    try:
        db = next(get_db())

        # Find subreddit (case-insensitive)
        subreddit_obj = (
            db.query(Subreddit)
            .filter(func.lower(Subreddit.name) == subreddit.lower())
            .first()
        )
        if not subreddit_obj:
            console.print(f"❌ Subreddit r/{subreddit} not found", style="red")
            raise typer.Exit(1)

        # Get posts with sentiment data from TextAnalysis table
        posts_with_sentiment = (
            db.query(Post, TextAnalysis)
            .join(TextAnalysis, Post.id == TextAnalysis.post_id)
            .filter(Post.subreddit_id == subreddit_obj.id)
            .limit(1000)
            .all()
        )

        if not posts_with_sentiment:
            console.print(
                f"📭 No posts with sentiment analysis found for r/{subreddit}",
                style="yellow",
            )
            console.print(
                "💡 Tip: Run 'reddit-analyzer data collect' to gather posts first",
                style="dim",
            )
            return

        # Use real sentiment analysis data
        sentiment_counts = {"positive": 0, "neutral": 0, "negative": 0}
        sentiment_scores = []
        confidence_scores = []

        # Sample posts for each sentiment
        sample_posts = {"positive": [], "neutral": [], "negative": []}

        for post, analysis in posts_with_sentiment:
            sentiment_label = analysis.sentiment_label.lower()
            if sentiment_label in sentiment_counts:
                sentiment_counts[sentiment_label] += 1
                sentiment_scores.append(analysis.sentiment_score)
                confidence_scores.append(analysis.confidence_score)

                # Collect sample posts (up to 3 per sentiment)
                if len(sample_posts[sentiment_label]) < 3:
                    sample_posts[sentiment_label].append(
                        {
                            "title": (
                                post.title[:60] + "..."
                                if len(post.title) > 60
                                else post.title
                            ),
                            "score": analysis.sentiment_score,
                        }
                    )

        console.print(f"😊 Sentiment Analysis for r/{subreddit}")

        # Display sentiment chart
        sentiment_chart = visualizer.sentiment_bar_chart(
            sentiment_counts, f"Sentiment Distribution - r/{subreddit}"
        )
        console.print(sentiment_chart)

        # Calculate and display statistics
        if sentiment_scores:
            avg_sentiment = sum(sentiment_scores) / len(sentiment_scores)
            avg_confidence = (
                sum(confidence_scores) / len(confidence_scores)
                if confidence_scores
                else 0
            )

            from rich.table import Table

            # Statistics table
            stats_table = Table(title="📊 Sentiment Statistics")
            stats_table.add_column("Metric", style="cyan")
            stats_table.add_column("Value", style="green")

            stats_table.add_row("Average Sentiment Score", f"{avg_sentiment:.3f}")
            stats_table.add_row("Average Confidence", f"{avg_confidence:.1%}")
            stats_table.add_row("Total Analyzed Posts", str(len(posts_with_sentiment)))

            sentiment_label = (
                "Positive"
                if avg_sentiment > 0.05
                else "Negative"
                if avg_sentiment < -0.05
                else "Neutral"
            )
            stats_table.add_row("Overall Sentiment", sentiment_label)

            console.print(stats_table)

            # Sample posts table
            for sentiment, posts_list in sample_posts.items():
                if posts_list:
                    sample_table = Table(
                        title=f"💬 Sample {sentiment.capitalize()} Posts"
                    )
                    sample_table.add_column("Post Title", style="cyan", max_width=60)
                    sample_table.add_column("Score", style="green")

                    for post_info in posts_list:
                        sample_table.add_row(
                            post_info["title"], f"{post_info['score']:.3f}"
                        )

                    console.print(sample_table)

        # Confidence distribution
        if confidence_scores:
            high_conf = sum(1 for c in confidence_scores if c >= 0.8)
            med_conf = sum(1 for c in confidence_scores if 0.5 <= c < 0.8)
            low_conf = sum(1 for c in confidence_scores if c < 0.5)

            conf_table = Table(title="🎯 Confidence Distribution")
            conf_table.add_column("Confidence Level", style="cyan")
            conf_table.add_column("Count", style="green")
            conf_table.add_column("Percentage", style="yellow")

            total = len(confidence_scores)
            conf_table.add_row(
                "High (≥80%)", str(high_conf), f"{high_conf / total * 100:.1f}%"
            )
            conf_table.add_row(
                "Medium (50-79%)", str(med_conf), f"{med_conf / total * 100:.1f}%"
            )
            conf_table.add_row(
                "Low (<50%)", str(low_conf), f"{low_conf / total * 100:.1f}%"
            )

            console.print(conf_table)

        # Export if requested
        if export:
            visualizer.export_chart(
                sentiment_counts, "pie", export, f"Sentiment Analysis - r/{subreddit}"
            )

    except Exception as e:
        console.print(f"❌ Error generating sentiment analysis: {e}", style="red")
        raise typer.Exit(1)
    finally:
        db.close()


@viz_app.command("activity")
@cli_auth.require_auth()
def show_activity(
    subreddit: Optional[str] = typer.Option(
        None, help="Specific subreddit (without r/)"
    ),
    period: str = typer.Option("24h", help="Time period: 24h, 7d, 30d"),
):
    """Show user activity trends."""
    try:
        db = next(get_db())

        # Parse period
        if period == "24h":
            hours = 24
            start_date = datetime.utcnow() - timedelta(hours=hours)
        elif period == "7d":
            hours = 24 * 7
            start_date = datetime.utcnow() - timedelta(days=7)
        elif period == "30d":
            hours = 24 * 30
            start_date = datetime.utcnow() - timedelta(days=30)
        else:
            console.print("❌ Invalid period. Use: 24h, 7d, 30d", style="red")
            raise typer.Exit(1)

        # Base query
        query = db.query(Post).filter(Post.created_at >= start_date)

        if subreddit:
            subreddit_obj = (
                db.query(Subreddit)
                .filter(func.lower(Subreddit.name) == subreddit.lower())
                .first()
            )
            if not subreddit_obj:
                console.print(f"❌ Subreddit r/{subreddit} not found", style="red")
                raise typer.Exit(1)
            query = query.filter(Post.subreddit_id == subreddit_obj.id)
            title_prefix = f"r/{subreddit}"
        else:
            title_prefix = "All Subreddits"

        posts = query.all()

        if not posts:
            console.print(
                "📭 No activity found for the specified criteria", style="yellow"
            )
            return

        # Analyze activity by hour
        hourly_activity = {}

        for post in posts:
            hour = post.created_at.strftime("%H")
            hourly_activity[hour] = hourly_activity.get(hour, 0) + 1

        # Fill missing hours with 0
        for hour in range(24):
            hour_str = f"{hour:02d}"
            if hour_str not in hourly_activity:
                hourly_activity[hour_str] = 0

        # Sort by hour
        sorted_activity = dict(sorted(hourly_activity.items()))

        console.print(f"📈 Activity Trends - {title_prefix} (Last {period})")

        # Create activity chart
        activity_chart = visualizer.horizontal_bar_chart(
            sorted_activity, f"Posts by Hour - {title_prefix}"
        )
        console.print(activity_chart)

        # Show peak hours
        peak_hour = max(sorted_activity, key=sorted_activity.get)
        peak_count = sorted_activity[peak_hour]

        console.print(
            f"🕐 Peak Activity: {peak_hour}:00 ({peak_count} posts)", style="green"
        )

    except Exception as e:
        console.print(f"❌ Error generating activity analysis: {e}", style="red")
        raise typer.Exit(1)
    finally:
        db.close()


@viz_app.command("subreddit-compare")
@cli_auth.require_auth()
def compare_subreddits(
    subreddits: str = typer.Argument(
        ..., help="Comma-separated list of subreddit names"
    ),
    metric: str = typer.Option(
        "posts", help="Metric to compare: posts, comments, score"
    ),
    days: int = typer.Option(7, help="Number of days to analyze"),
):
    """Compare metrics across multiple subreddits."""
    try:
        db = next(get_db())

        subreddit_names = [name.strip() for name in subreddits.split(",")]

        if len(subreddit_names) < 2:
            console.print(
                "❌ Please provide at least 2 subreddits to compare", style="red"
            )
            raise typer.Exit(1)

        # Calculate date range
        start_date = datetime.utcnow() - timedelta(days=days)

        comparison_data = {}

        for subreddit_name in subreddit_names:
            subreddit_obj = (
                db.query(Subreddit)
                .filter(func.lower(Subreddit.name) == subreddit_name.lower())
                .first()
            )

            if not subreddit_obj:
                console.print(
                    f"⚠️  Subreddit r/{subreddit_name} not found, skipping",
                    style="yellow",
                )
                continue

            posts = (
                db.query(Post)
                .filter(
                    Post.subreddit_id == subreddit_obj.id, Post.created_at >= start_date
                )
                .all()
            )

            if metric == "posts":
                value = len(posts)
            elif metric == "comments":
                value = sum(post.num_comments for post in posts)
            elif metric == "score":
                value = sum(post.score for post in posts)
            else:
                console.print(f"❌ Invalid metric: {metric}", style="red")
                raise typer.Exit(1)

            comparison_data[f"r/{subreddit_name}"] = value

        if not comparison_data:
            console.print("❌ No valid subreddits found", style="red")
            raise typer.Exit(1)

        console.print(f"📊 Subreddit Comparison - {metric.title()} (Last {days} days)")

        # Create comparison chart
        comparison_chart = visualizer.horizontal_bar_chart(
            comparison_data, f"Subreddit Comparison - {metric.title()}"
        )
        console.print(comparison_chart)

    except Exception as e:
        console.print(f"❌ Error comparing subreddits: {e}", style="red")
        raise typer.Exit(1)
    finally:
        db.close()
