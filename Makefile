.PHONY: gate

# The template's own gate, and the target its hosted CI job runs.
#
# This repository is a cookiecutter template rather than a package: nothing at its root installs,
# and its real subject is the repository it renders. So its gate is the render gate, every row of
# the name-length matrix in scripts/verify-render.sh rendered and put through the rendered
# repository's own gate and the proofs around it. Any failure in any row fails this target.
#
# It needs `uv` on PATH, which requirements-dev.lock pins, and network access: it clones the four
# commons at the commits cookiecutter.json pins, and resolves each render's tools and interpreter
# through uv. It takes minutes, not seconds, which is the accepted price of proving the thing
# every new repository starts from.
gate:
	scripts/verify-render.sh
