import subprocess

subprocess.run(
	[
		'bunx',
		'@tailwindcss/cli',
		'-i',
		'src/tailwind.css',
		'-o',
		'static/css/daisy.min.css',
		'--minify',
	],
	check=True,
)
