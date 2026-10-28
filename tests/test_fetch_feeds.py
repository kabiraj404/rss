import sys

sys.path.append("scripts")
from scripts.fetch_feeds import RSSHub
import feedparser
import os
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
import pytest


@pytest.fixture
def opml_file(tmp_path):
    return create_mock_opml_file(tmp_path)


@pytest.fixture
def config_file(tmp_path):
    return create_mock_config_file(tmp_path)


@pytest.fixture
def hub(opml_file, config_file, tmp_path):
    return create_mock_hub(opml_file, config_file, tmp_path)


def create_mock_opml_file(tmp_path):
    opml_content = """
    <opml version="1.0">
        <body>
            <outline text="Feed 1" title="Feed 1" type="rss" xmlUrl="http://example.com/feed1.xml"/>
            <outline text="Feed 2" title="Feed 2" type="rss" xmlUrl="http://example.com/feed2.xml"/>
        </body>
    </opml>
    """
    opml_file = tmp_path / "rss.opml"
    opml_file.write_text(opml_content)
    return str(opml_file)


def create_mock_config_file(tmp_path):
    config_content = """
    {
        "site_title": "Test Site",
        "site_description": "Test Description",
        "site_link": "http://example.com",
        "generator": "TestGenerator/1.0",
        "output_files": {
            "rss": "test_rss.xml",
            "feeds": "test_feeds.xml",
            "html": "test_index.html"
        },
        "max_entries": {
            "rss": 1,
            "html": 1
        }
    }
    """
    config_file = tmp_path / "config.json"
    config_file.write_text(config_content)
    return str(config_file)


def create_mock_hub(opml_file, config_file, tmp_path):
    hub = RSSHub(opml_file=opml_file, config_file=config_file)
    hub.all_entries = [
        feedparser.FeedParserDict(
            {
                "title": "Entry 1",
                "link": "http://example.com/entry1",
                "summary": "Summary 1",
                "published": "2023-10-27T10:00:00Z",
                "feed_title": "Feed 1",
                "feed_url": "http://example.com/feed1.xml",
            }
        ),
        feedparser.FeedParserDict(
            {
                "title": "Entry 2",
                "link": "http://example.com/entry2",
                "summary": "Summary 2",
                "published": "2023-10-26T10:00:00Z",
                "feed_title": "Feed 2",
                "feed_url": "http://example.com/feed2.xml",
            }
        ),
    ]
    hub.feeds_with_updates = [
        {"title": "Feed 1", "url": "http://example.com/feed1.xml"},
        {"title": "Feed 2", "url": "http://example.com/feed2.xml"},
    ]
    os.chdir(tmp_path)
    return hub


def test_parse_opml(opml_file, config_file):
    hub = RSSHub(opml_file=opml_file, config_file=config_file)
    feeds = hub.parse_opml()
    assert len(feeds) == 2
    assert feeds[0]["title"] == "Feed 1"
    assert feeds[0]["url"] == "http://example.com/feed1.xml"
    assert feeds[1]["title"] == "Feed 2"
    assert feeds[1]["url"] == "http://example.com/feed2.xml"


def test_parse_opml_includes_html_only_sources(tmp_path, config_file):
    opml_content = """
    <opml version="1.0">
        <body>
            <outline text="Magnum Photos" title="Magnum Photos" htmlUrl="https://www.magnumphotos.com/"/>
        </body>
    </opml>
    """
    opml_file = tmp_path / "rss.opml"
    opml_file.write_text(opml_content)

    hub = RSSHub(opml_file=str(opml_file), config_file=config_file)
    feeds = hub.parse_opml()

    assert len(feeds) == 1
    assert feeds[0]["title"] == "Magnum Photos"
    assert feeds[0]["url"] == "https://www.magnumphotos.com/"
    assert feeds[0]["rss_url"] == ""
    assert feeds[0]["html_url"] == "https://www.magnumphotos.com/"


def test_generate_latest_rss(hub):
    hub.generate_latest_rss()
    rss_file = hub.config["output_files"]["rss"]
    assert os.path.exists(rss_file)
    with open(rss_file, "r") as f:
        content = f.read()
        assert "<title>Test Site</title>" in content
        assert "<link>http://example.com</link>" in content
        assert "<description>Test Description</description>" in content
        assert "<generator>TestGenerator/1.0</generator>" in content
        assert "<title>Entry 1</title>" in content
        assert "<title>Entry 2</title>" not in content


def test_generate_latest_feeds(hub):
    hub.generate_latest_feeds()
    feeds_file = hub.config["output_files"]["feeds"]
    assert os.path.exists(feeds_file)
    with open(feeds_file, "r") as f:
        content = f.read()

        assert "<title>Feed 1</title>" in content


def test_generate_html(hub):
    site_data = hub.generate_site_data()
    hub.generate_html(site_data)
    html_file = hub.config["output_files"]["html"]
    assert os.path.exists(html_file)
    with open(html_file, "r") as f:
        content = f.read()
        assert "<title>Test Site</title>" in content
        assert "Test Site" in content
        assert "Test Description" in content
        assert "Latest Articles" in content


def test_generate_site_data_includes_latest_entries(hub):
    today = datetime.now(timezone.utc)
    for index, entry in enumerate(hub.all_entries):
        entry["published"] = (today - timedelta(days=index)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        entry["published_parsed"] = (
            today - timedelta(days=index)
        ).timetuple()
    site_data = hub.generate_site_data()
    assert "latest_entries" in site_data
    assert len(site_data["latest_entries"]) == 2
    assert site_data["latest_entries"][0]["title"] == "Entry 1"


def test_latest_articles_keep_ten_per_category_per_day(hub):
    entries = []
    today = datetime.now(timezone.utc).date()
    days = [today - timedelta(days=offset) for offset in (0, 1)]
    for day in days:
        for category in ("Technology", "News"):
            for index in range(12):
                entries.append(
                    feedparser.FeedParserDict(
                        {
                            "title": f"{category} {day} {index}",
                            "link": f"http://example.com/{day}/{category}/{index}",
                            "published": f"{day}T{index:02d}:00:00Z",
                            "published_parsed": (
                                day.year,
                                day.month,
                                day.day,
                                index,
                                0,
                                0,
                                0,
                                0,
                                0,
                            ),
                            "feed_category": category,
                            "feed_title": category,
                        }
                    )
                )
    hub.all_entries = entries

    site_data = hub.generate_site_data()

    assert set(site_data["latest_entries_by_day"]) == {
        day.isoformat() for day in days
    }
    assert all(
        len(entries) == 10
        for categories in site_data["latest_entries_by_day"].values()
        for entries in categories.values()
    )
    assert site_data["latest_entries_by_day"][days[0].isoformat()]["Technology"][
        0
    ]["title"] == f"Technology {days[0]} 11"


def test_latest_articles_exclude_entries_older_than_three_days(hub):
    now = datetime.now(timezone.utc)
    today = now.date()
    included_date = now - timedelta(days=2)
    hub.all_entries = [
        feedparser.FeedParserDict(
            {
                "title": "Included",
                "published_parsed": included_date.timetuple(),
                "feed_category": "News",
            }
        ),
        feedparser.FeedParserDict(
            {
                "title": "Excluded",
                "published": (today - timedelta(days=3)).isoformat(),
                "feed_category": "News",
            }
        ),
    ]

    site_data = hub.generate_site_data()

    assert "Included" in [entry["title"] for entry in site_data["latest_entries"]]
    assert "Excluded" not in [entry["title"] for entry in site_data["latest_entries"]]
