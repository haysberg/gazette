import os
import time
from datetime import datetime
from time import struct_time
from types import SimpleNamespace

import feedparser
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from utils.models import (
	PAYWALL_RE,
	Feed,
	Post,
	_entry_excerpt,
	_entry_image,
	_parsed_datetime,
	_retry_delay,
)


def make_entry(link: str, title: str = 'Titre') -> feedparser.FeedParserDict:
	return feedparser.FeedParserDict({'link': link, 'title': title})


def test_parsed_datetime_converts_utc_to_local():
	# feedparser's *_parsed fields are UTC. Reinterpreting them as local time via
	# mktime shifted every date by the server's UTC offset (12:00 UTC was stored
	# as 14:00 UTC-2h, i.e. shown two hours in the past).
	previous_tz = os.environ.get('TZ')
	os.environ['TZ'] = 'Europe/Paris'
	time.tzset()
	try:
		parsed = struct_time((2026, 9, 13, 12, 0, 0, 0, 0, 0))
		assert _parsed_datetime(parsed) == datetime(2026, 9, 13, 14, 0, 0)
	finally:
		if previous_tz is None:
			os.environ.pop('TZ', None)
		else:
			os.environ['TZ'] = previous_tz
		time.tzset()


def test_retry_delay_grows_then_caps():
	assert _retry_delay(1) == 15 * 60
	assert _retry_delay(2) == 30 * 60
	assert _retry_delay(50) == 6 * 60 * 60


def test_store_entries_counts_only_new_links():
	engine = create_engine(
		'sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool
	)
	SQLModel.metadata.create_all(engine)

	with Session(engine) as session:
		feed = Feed(link='https://exemple.org/rss', domain='exemple.org', title='Exemple')
		session.add(feed)
		session.commit()

		data = SimpleNamespace(entries=[make_entry('https://exemple.org/a')])
		assert feed._store_entries(data, session) == 1
		session.commit()
		# A feed that ignores conditional GETs re-serves the same entries; they
		# must not be reported as new content.
		assert feed._store_entries(data, session) == 0
		# A genuinely new link is counted.
		data.entries.append(make_entry('https://exemple.org/b'))
		assert feed._store_entries(data, session) == 1


def test_undated_entry_keeps_first_seen_date():
	engine = create_engine(
		'sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool
	)
	SQLModel.metadata.create_all(engine)

	with Session(engine) as session:
		feed = Feed(link='https://exemple.org/rss', domain='exemple.org', title='Exemple')
		session.add(feed)
		session.commit()

		data = SimpleNamespace(entries=[make_entry('https://exemple.org/a')])
		assert feed._store_entries(data, session) == 1
		session.commit()
		first = session.get(Post, 'https://exemple.org/a').publication_date

		# A feed that keeps re-serving an entry without a date must not bump it to
		# "now" on every cycle, which made it leapfrog to the top of the page.
		assert feed._store_entries(data, session) == 0
		session.commit()
		again = session.get(Post, 'https://exemple.org/a').publication_date
		assert again == first


def test_paywall_regex_matches_markers_without_false_positives():
	assert PAYWALL_RE.search('Vous lisez un article réservé aux abonnés.')
	assert PAYWALL_RE.search('"isAccessibleForFree": false')
	assert PAYWALL_RE.search('This is a subscriber-only article')
	# Newsletter/subscription prompts on free pages must not flag the article.
	assert not PAYWALL_RE.search("Abonnez-vous à notre newsletter")
	assert not PAYWALL_RE.search('Nos abonnés nous soutiennent')


def test_entry_excerpt_strips_markup_and_image_is_extracted():
	entry = feedparser.FeedParserDict(
		{
			'summary': '<p>Bonjour <b>le</b> monde</p>',
			'media_thumbnail': [{'url': 'https://exemple.org/img.jpg'}],
		}
	)
	assert _entry_excerpt(entry) == 'Bonjour le monde'
	assert _entry_image(entry) == 'https://exemple.org/img.jpg'


def test_entry_image_ignores_non_http_urls():
	entry = feedparser.FeedParserDict({'media_thumbnail': [{'url': 'javascript:alert(1)'}]})
	assert _entry_image(entry) is None
