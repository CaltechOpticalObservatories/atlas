# Development

atlas uses [tox](https://tox.wiki/) to run its checks and build these docs, so
every task has one command that works the same on a laptop and in CI.

## Install tox

tox is the only thing you install globally; it creates and manages the
environment for each task itself.

```sh
pipx install tox        # recommended, keeps tox out of your project env
```

or

```sh
python -m pip install --user tox
```

or, if you already use [uv](https://docs.astral.sh/uv/):

```sh
uv tool install tox --with tox-uv
```

## Run everything

```sh
tox
```

That runs the default environments: the test suite and pylint, the same two
checks the GitHub Actions workflows run on every push.

## Run one task

```sh
tox -e tests        # pytest
tox -e lint         # pylint, using .pylintrc
tox -e docs         # build the HTML documentation
tox -e serve        # build the docs and watch for changes
```

`tox list` shows all four with their descriptions, and `tox -e tests -- -k statistics` passes arguments
through to the underlying tool, here to pytest.

## The environments

| Environment | Runs | Notes |
| --- | --- | --- |
| `tests` | `pytest` | Sets `QT_QPA_PLATFORM=offscreen`, so no display is needed |
| `lint` | `pylint` over every tracked `.py` | Uses the repository `.pylintrc` |
| `docs` | `sphinx-build -W` | Warnings are errors; a broken link fails the build |
| `serve` | `sphinx-autobuild` | Serves on <http://127.0.0.1:8000> and rebuilds on save |

`tests` and `lint` install atlas with the `dev` and `zmq` extras. `docs`
installs only the `docs` extra and **not** atlas itself, so building the
documentation needs no Qt and no display.

## Documentation

The docs are [Sphinx](https://www.sphinx-doc.org/) with the
[Shibuya](https://shibuya.lepture.com/) theme, written in Markdown through
[MyST](https://myst-parser.readthedocs.io/).

```sh
tox -e docs
open docs/_build/html/index.html
```

While writing, `tox -e serve` is the better loop: it rebuilds on save and
reloads the browser.

### Adding a page

1. Create `docs/your-page.md`.
2. Add it to a `toctree` in `docs/index.md`, under whichever caption fits.
3. Run `tox -e docs` and fix anything it reports.

Because the build runs with `-W`, a page missing from every toctree, a link to
a heading that does not exist, or a malformed directive all fail the build
rather than producing a quietly broken site.

### Cross-references

Link to another page with an empty link text and MyST fills in its title:

```markdown
See [](configuration) for the full list.
```

Link to a heading with the file and its anchor:

```markdown
See [](live.md#shared-memory).
```

Anchors are generated for headings down to three levels deep
(`myst_heading_anchors = 3`). Where a heading's own anchor would be awkward to
depend on, the page defines an explicit one with `(name)=` above the heading.

### Without tox

If you would rather drive Sphinx directly, do it through the interpreter rather
than through the `sphinx-build` script:

```sh
python -m venv .venv
source .venv/bin/activate
pip install -e ".[docs]"
python -m sphinx -b html -W docs docs/_build/html
```

:::{warning}
Use `python -m sphinx`, not bare `sphinx-build`. If any other Python on the
machine also has Sphinx installed, a stale entry on `PATH` can win over the
virtual environment's, and you get a confusing failure from a Sphinx that has
none of the extensions:

```text
Could not import extension sphinx_copybutton
    (exception: No module named 'sphinx_copybutton')
```

Note the `Python version:` line in that error report: it names the interpreter
that actually ran, which is the quickest way to spot the mismatch. `python -m
sphinx` cannot pick the wrong one. `tox -e docs` is immune for the same reason,
since it builds in its own isolated environment.
:::

## Testing

```sh
tox -e tests
```

Tests live in `tests/` and run under pytest with `--strict-markers` and
`--strict-config`, so an unregistered mark or a typo'd fixture fails rather
than skipping quietly. The Qt tests run headless via `QT_QPA_PLATFORM=offscreen`.

`scripts/demo_shm_viewer.py` is a manual demo rather than a test. It launches
the real window against a synthetic 60 Hz producer so the
[live path](live.md#shared-memory) can be exercised without a detector; pytest
does not collect it.

## Linting

```sh
tox -e lint
```

pylint runs over every tracked Python file with the repository `.pylintrc`. CI
runs exactly the same command, so a clean `tox -e lint` means a clean CI run.

## Continuous integration

Three workflows run on every push:

| Workflow | Does | Equivalent |
| --- | --- | --- |
| `.github/workflows/tests.yml` | pytest on Python 3.12 | `tox -e tests` |
| `.github/workflows/pylint.yml` | pylint on Python 3.12 | `tox -e lint` |
| `.github/workflows/docs.yml` | Builds the documentation | `tox -e docs` |

The docs job runs `tox -e docs` rather than calling Sphinx itself, so the
dependency list and the `-W` flag have one definition rather than two. Because
that environment sets `skip_install`, the job needs neither Qt nor a matching
Python,
and it finishes in a few seconds.

It uploads the built site as a `docs-html` artifact, kept for 14 days. That is
the quickest way to read a documentation change as rendered HTML before merging
it: open the run's summary page and download the artifact.

## Reporting issues

Please open an issue on the
[GitHub Issues page](https://github.com/CaltechOpticalObservatories/atlas/issues).
Your feedback helps us improve the project.
