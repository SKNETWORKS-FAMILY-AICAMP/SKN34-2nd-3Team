from service.comment_sentiment_service import CommentSentimentService


class FakeRepository:
    def get_novel_comment_sentiment_overview(self, novel_id):
        assert novel_id == 10
        return {
            "stored_comment_count": 12,
            "analyzed_comment_count": 10,
            "positive_count": 6,
            "neutral_count": 3,
            "negative_count": 1,
            "average_confidence": 0.85,
        }

    def get_episode_comment_sentiment_summaries(self, novel_id):
        return [
            {
                "episode_id": 1,
                "analyzed_comment_count": 4,
                "positive_count": 2,
                "neutral_count": 1,
                "negative_count": 1,
            }
        ]

    def get_episode_comments_with_sentiment(self, episode_id, **kwargs):
        return [{"comment_id": 1, "episode_id": episode_id}]

    def get_representative_episode_comments(self, episode_id, **kwargs):
        return {
            "positive": [],
            "negative": [],
            "ambiguous": [],
            "controversy": [],
        }


def test_overview_ratios():
    service = CommentSentimentService(FakeRepository())
    result = service.get_novel_overview(10)

    assert result["positive_ratio"] == 60.0
    assert result["neutral_ratio"] == 30.0
    assert result["negative_ratio"] == 10.0
    assert result["reaction_score"] == 50.0
    assert result["reliability"] == "참고용"


def test_episode_summary_ratios():
    service = CommentSentimentService(FakeRepository())
    result = service.get_episode_summaries(10)[0]

    assert result["positive_ratio"] == 50.0
    assert result["negative_ratio"] == 25.0
    assert result["reaction_score"] == 25.0
    assert result["reliability"] == "표본 매우 적음"
