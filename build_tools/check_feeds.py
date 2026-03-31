import tomllib
from concurrent.futures import ThreadPoolExecutor, as_completed

import feedparser

TIMEOUT = 15
USER_AGENT = 'Mozilla/5.0 (compatible; Gazette/1.0; +https://github.com)'

with open('gazette.toml', 'rb') as f:
	config = tomllib.load(f)

feeds = config['feeds']['feedlist']
print(f'Checking {len(feeds)} feeds…\n')

errors = []


def check_feed(feed):
	title = feed['title']
	url = feed['link']
	try:
		result = feedparser.parse(
			url,
			request_headers={'User-Agent': USER_AGENT},
		)
		if result.bozo and not result.entries:
			return (title, url, f'Parse error: {result.bozo_exception}')
		if not result.entries:
			return (title, url, 'No entries found')
		return (title, url, None)
	except Exception as e:
		return (title, url, str(e))


with ThreadPoolExecutor(max_workers=10) as pool:
	futures = {pool.submit(check_feed, feed): feed for feed in feeds}
	for future in as_completed(futures):
		title, url, error = future.result()
		if error:
			errors.append((title, url, error))
			print(f'  FAIL  {title} — {error}')
		else:
			print(f'  OK    {title}')

print(f'\n{len(feeds) - len(errors)}/{len(feeds)} feeds OK.')
if errors:
	print(f'{len(errors)} feed(s) with errors:')
	for title, url, error in errors:
		print(f'  - {title}: {url}')
		print(f'    {error}')
