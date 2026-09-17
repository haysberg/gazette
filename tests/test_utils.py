from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from types import SimpleNamespace

from utils.utils import _enclosure_type, _jinja_env, _rfc822, _timeago


def test_runtime_environment_autoescapes_feed_content():
	rendered = _jinja_env.from_string('{{ value }}').render(value='<script>alert(1)</script>')
	assert '<script>' not in rendered
	assert '&lt;script&gt;' in rendered


def test_rss_template_escapes_titles_and_keeps_wall_clock():
	template = _jinja_env.get_template('feed.xml')
	feed = SimpleNamespace(link='https://exemple.org/rss', title='Exemple')
	post = SimpleNamespace(
		link='https://exemple.org/a',
		title="<b>Pas d'HTML</b>",
		publication_date=datetime(2026, 9, 13, 14, 0),
		feed=feed,
	)

	output = template.render(posts=[post], build_date=datetime(2026, 9, 13, 14, 0))

	assert '<b>' not in output
	assert '&lt;b&gt;' in output

	raw_date = output.split('<pubDate>', 1)[1].split('</pubDate>', 1)[0]
	parsed = parsedate_to_datetime(raw_date)
	assert parsed.tzinfo is not None
	assert parsed.replace(tzinfo=None) == datetime(2026, 9, 13, 14, 0)


def test_rfc822_keeps_wall_clock_and_has_offset():
	parsed = parsedate_to_datetime(_rfc822(datetime(2026, 9, 13, 14, 0)))
	assert parsed.tzinfo is not None
	assert parsed.replace(tzinfo=None) == datetime(2026, 9, 13, 14, 0)


def test_enclosure_type_from_extension():
	assert _enclosure_type('https://exemple.org/a.png') == 'image/png'
	assert _enclosure_type('https://exemple.org/a.webp?size=2') == 'image/webp'
	assert _enclosure_type('https://exemple.org/a') == 'image/jpeg'


def test_source_template_escapes_title_and_omits_excerpt():
	template = _jinja_env.get_template('source.html')
	feed = SimpleNamespace(
		domain='exemple.org',
		title='Exemple',
		subtitle='',
		link='https://exemple.org/rss',
	)
	post = SimpleNamespace(
		link='https://exemple.org/a',
		title='<b>Titre</b>',
		excerpt='<i>resume</i>',
		publication_date=datetime(2026, 9, 13, 14, 0),
	)
	output = template.render(
		feed=feed,
		posts=[post],
		css_hash='c',
		style_hash='s',
		js_hash='j',
		canonical_url='https://insoumis.news/source/exemple.org/',
	)
	assert '<b>Titre</b>' not in output
	assert '&lt;b&gt;Titre&lt;/b&gt;' in output
	# Summaries are no longer rendered on the served pages.
	assert 'resume' not in output


def test_timeago_buckets():
	now = datetime.now()
	assert _timeago(now) == "À l'instant"
	assert _timeago(now - timedelta(minutes=5)) == 'Il y a 5 min'
	assert _timeago(now - timedelta(hours=3)) == 'Il y a 3h'
	assert _timeago(now - timedelta(days=2)) == 'Il y a 2j'
