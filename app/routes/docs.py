"""
Documentation routes - Renders markdown files from docs/ folder
"""
from flask import Blueprint, render_template, abort, current_app
import os
import markdown
import re
from markupsafe import Markup

docs_bp = Blueprint('docs', __name__)

# Documentation structure with metadata
DOCS_STRUCTURE = [
    {
        'section': 'Démarrage',
        'pages': [
            {'slug': 'index', 'title': 'Introduction', 'icon': 'home'},
            {'slug': 'getting-started', 'title': 'Premiers pas', 'icon': 'rocket'},
        ]
    },
    {
        'section': 'Guide utilisateur',
        'pages': [
            {'slug': 'quiz-syntax', 'title': 'Syntaxe des quiz', 'icon': 'page-edit'},
            {'slug': 'admin-guide', 'title': 'Administration', 'icon': 'settings'},
            {'slug': 'groups-tenants', 'title': 'Groupes & Tenants', 'icon': 'building'},
            {'slug': 'i18n', 'title': 'Langues (i18n)', 'icon': 'language'},
        ]
    },
    {
        'section': 'Technique',
        'pages': [
            {'slug': 'self-hosting', 'title': 'Auto-hébergement', 'icon': 'server'},
            {'slug': 'configuration', 'title': 'Configuration', 'icon': 'tools'},
            {'slug': 'api', 'title': 'API', 'icon': 'code'},
        ]
    },
]


def get_docs_path():
    """Get the path to the docs folder."""
    return os.path.join(current_app.root_path, '..', 'docs')


def get_doc_content(slug):
    """Read and parse a markdown file from the docs folder."""
    # Validate slug format - only allow alphanumeric, hyphens (no path traversal)
    if not slug or not re.match(r'^[a-zA-Z0-9\-]+$', slug):
        return None, None, None

    docs_path = os.path.realpath(get_docs_path())
    file_path = os.path.realpath(os.path.join(docs_path, f'{slug}.md'))

    # Verify the resolved path is within docs directory (prevent path traversal)
    if not file_path.startswith(docs_path + os.sep):
        return None, None, None

    if not os.path.exists(file_path):
        return None, None, None

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Extract title from first # heading
    title_match = re.match(r'^#\s+(.+)$', content, re.MULTILINE)
    title = title_match.group(1) if title_match else slug.replace('-', ' ').title()

    # Convert markdown to HTML with extensions
    md = markdown.Markdown(extensions=[
        'fenced_code',
        'tables',
        'toc',
        'codehilite',
        'attr_list',
        'md_in_html',
    ])
    html_content = md.convert(content)
    toc = getattr(md, 'toc', '')

    return Markup(html_content), title, Markup(toc)


def get_page_info(slug):
    """Get page metadata from DOCS_STRUCTURE."""
    for section in DOCS_STRUCTURE:
        for page in section['pages']:
            if page['slug'] == slug:
                return page
    return None


def get_nav_links(current_slug):
    """Get previous and next page links for navigation."""
    all_pages = []
    for section in DOCS_STRUCTURE:
        all_pages.extend(section['pages'])

    current_idx = None
    for i, page in enumerate(all_pages):
        if page['slug'] == current_slug:
            current_idx = i
            break

    prev_page = all_pages[current_idx - 1] if current_idx and current_idx > 0 else None
    next_page = all_pages[current_idx + 1] if current_idx is not None and current_idx < len(all_pages) - 1 else None

    return prev_page, next_page


@docs_bp.route('/')
def index():
    """Documentation home page."""
    return page('index')


@docs_bp.route('/<slug>')
def page(slug):
    """Render a documentation page."""
    result = get_doc_content(slug)

    if result[0] is None:
        abort(404)

    content, title, toc = result
    page_info = get_page_info(slug)
    prev_page, next_page = get_nav_links(slug)

    return render_template('docs/page.html',
                         content=content,
                         title=title,
                         toc=toc,
                         current_slug=slug,
                         page_info=page_info,
                         docs_structure=DOCS_STRUCTURE,
                         prev_page=prev_page,
                         next_page=next_page)
