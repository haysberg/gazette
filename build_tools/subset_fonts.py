"""Subset the self-hosted Config fonts into latin and latin-ext slices.

The full woff2 files in build_tools/font_sources are committed sources, not
served. For each one this writes a `latin` and a `latin-ext` slice next to the
other static assets. style.css declares both with matching `unicode-range`, so a
French page only downloads the ~13 KB latin slice and the larger ext slice is
fetched only if a glyph outside latin actually appears (rare article titles).
"""

import os

from fontTools.subset import Options, Subsetter, parse_unicodes
from fontTools.ttLib import TTFont

SOURCES_DIR = os.path.join('build_tools', 'font_sources')
OUTPUT_DIR = os.path.join('static', 'fonts')

# Ranges match the Google Fonts latin / latin-ext slices. Latin covers French
# (accents live in Latin-1 Supplement) and common punctuation.
SLICES = {
	'latin': 'U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,'
	'U+0304,U+0308,U+0329,U+2000-206F,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD',
	'latin-ext': 'U+0100-02AF,U+0304,U+0308,U+0329,U+1E00-1E9F,U+1EF2-1EFF,U+2020,'
	'U+20A0-20AB,U+20AD-20CF,U+2113,U+2C60-2C7F,U+A720-A7FF',
}


def subset_font(source_path: str, output_path: str, unicode_range: str) -> None:
	font = TTFont(source_path)
	# Do not stamp `head.modified` with the current time: it makes the woff2
	# bytes (and thus the git diff) change on every run even when the subset is
	# identical.
	font.recalcTimestamp = False
	options = Options()
	options.flavor = 'woff2'
	# Keep every OpenType layout feature (kerning, ligatures, contextual forms)
	# so shaping stays identical to the full font.
	options.layout_features = ['*']
	subsetter = Subsetter(options=options)
	subsetter.populate(unicodes=parse_unicodes(unicode_range))
	subsetter.subset(font)
	font.flavor = 'woff2'
	font.save(output_path)


def main() -> None:
	os.makedirs(OUTPUT_DIR, exist_ok=True)
	for filename in sorted(os.listdir(SOURCES_DIR)):
		if not filename.endswith('.woff2'):
			continue
		stem = filename.removesuffix('.woff2')
		for label, unicode_range in SLICES.items():
			source = os.path.join(SOURCES_DIR, filename)
			output = os.path.join(OUTPUT_DIR, f'{stem}-{label}.woff2')
			subset_font(source, output, unicode_range)
			print(f'{filename} -> {os.path.basename(output)} ({os.path.getsize(output)} B)')


if __name__ == '__main__':
	main()
