"""Sphinx configuration for the atlas documentation."""
# Sphinx reads its settings from lowercase module-level names, so the
# constant-naming rule does not apply to this file.
# pylint: disable=invalid-name

from importlib.metadata import PackageNotFoundError, version as package_version

project = "atlas"
author = "Caltech Optical Observatories"
copyright = "2026, Caltech Optical Observatories"  # pylint: disable=redefined-builtin

try:
    release = package_version("atlas")
except PackageNotFoundError:
    # The docs build does not need atlas importable, so an uninstalled
    # checkout should still produce a complete set of pages.
    release = "0.1.0"
version = release

extensions = [
    "myst_parser",
    "sphinx_copybutton",
    "sphinx_design",
]

source_suffix = {".md": "markdown", ".rst": "restructuredtext"}
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# Markdown niceties used across the guide: ``:::{note}`` blocks, tables with
# footnotes, and literal dashes that should not turn into typographic ones.
myst_enable_extensions = [
    "colon_fence",
    "deflist",
    "linkify",
    "substitution",
]
myst_heading_anchors = 3

html_theme = "shibuya"
html_static_path = ["_static"]
html_css_files = ["custom.css"]
html_title = "atlas"
html_copy_source = False
html_show_sourcelink = False

html_theme_options = {
    "accent_color": "cyan",
    "github_url": "https://github.com/CaltechOpticalObservatories/atlas",
    "nav_links": [
        {"title": "Install", "url": "installation"},
        {"title": "Quickstart", "url": "quickstart"},
        {"title": "Configuration", "url": "configuration"},
        {"title": "Issues",
         "url": "https://github.com/CaltechOpticalObservatories/atlas/issues"},
    ],
    "globaltoc_expand_depth": 1,
}

# Powers the theme's "Edit this page" and repository links.
html_context = {
    "source_type": "github",
    "source_user": "CaltechOpticalObservatories",
    "source_repo": "atlas",
    "source_version": "main",
    "source_docs_path": "/docs/",
}

# Keep the copy button from grabbing shell prompts and REPL markers.
copybutton_prompt_text = r">>> |\.\.\. |\$ "
copybutton_prompt_is_regexp = True
