"""Precompression helpers shared by the build tools and the runtime generator.

Every file served by Gazette gets brotli and gzip siblings written next to it so
the web server can hand them straight to the client (static-web-server's
`compression-static`, Caddy's `precompressed`) instead of compressing on every
request. Pages rendered at runtime go through the same path as build-time assets,
which also keeps a page and its `.br`/`.gz` copies from drifting apart.
"""

import gzip
import os

import brotli

# Build-time quality: slow to produce, but paid once per 15-minute regeneration
# rather than once per request.
BROTLI_QUALITY = 11


def write_compressed(path: str, data: str | bytes, *, quality: int = BROTLI_QUALITY) -> None:
	"""Write `data` to `path` along with `.br` and `.gz` siblings.

	Each file is written to a temporary name and then moved into place, so a
	request that lands mid-write never sees a truncated file. The compressed
	copies land before the plain one: a client that accepts brotli then reads
	either the previous page or the new one, never a `.br` that is newer than
	the page it claims to represent.
	"""
	raw = data.encode('utf-8') if isinstance(data, str) else data

	_replace(path + '.br', brotli.compress(raw, quality=quality))
	_replace(path + '.gz', gzip.compress(raw))
	_replace(path, raw)


def _replace(path: str, data: bytes) -> None:
	tmp = f'{path}.tmp'
	with open(tmp, 'wb') as f:
		f.write(data)
	os.replace(tmp, path)
