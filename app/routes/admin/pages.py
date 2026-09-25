"""Custom content pages (superadmin)."""
from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required
from flask_babel import lazy_gettext as _l
from app import db
from app.routes.admin import admin_bp
from app.routes.admin.common import superadmin_required


@admin_bp.route('/pages')
@login_required
@superadmin_required
def pages():
    """List all custom pages."""
    from app.models.page import Page
    all_pages = Page.query.order_by(Page.display_order, Page.title).all()
    return render_template('admin/pages.html', pages=all_pages)


@admin_bp.route('/pages/create', methods=['GET', 'POST'])
@login_required
@superadmin_required
def create_page():
    """Create a new custom page."""
    from app.models.page import Page
    import re

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        slug = request.form.get('slug', '').strip().lower()
        content = request.form.get('content', '')
        location = request.form.get('location', 'footer')
        display_order = int(request.form.get('display_order', 0) or 0)
        is_published = request.form.get('is_published') == 'on'
        open_new_tab = request.form.get('open_new_tab') == 'on'

        # Validate
        if not title:
            flash(_l('Le titre est requis'), 'error')
            return render_template('admin/edit_page.html', page=None)

        # Generate slug if not provided
        if not slug:
            slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')

        # Check slug uniqueness
        existing = Page.query.filter_by(slug=slug).first()
        if existing:
            flash(_l('Ce slug existe deja'), 'error')
            return render_template('admin/edit_page.html', page=None)

        # Validate slug format
        if not re.match(r'^[a-z0-9\-]+$', slug):
            flash(_l('Le slug ne peut contenir que des lettres minuscules, chiffres et tirets'), 'error')
            return render_template('admin/edit_page.html', page=None)

        page = Page(
            title=title,
            slug=slug,
            content=content,
            location=location,
            display_order=display_order,
            is_published=is_published,
            open_new_tab=open_new_tab
        )
        db.session.add(page)
        db.session.commit()

        flash(_l('Page creee avec succes'), 'success')
        return redirect(url_for('admin.pages'))

    return render_template('admin/edit_page.html', page=None)


@admin_bp.route('/pages/<identifier>/edit', methods=['GET', 'POST'])
@login_required
@superadmin_required
def edit_page(identifier):
    """Edit an existing custom page."""
    from app.models.page import Page
    import re

    page = Page.get_by_identifier(identifier)
    if not page:
        flash(_l('Page introuvable'), 'error')
        return redirect(url_for('admin.pages'))

    # Redirect if accessed by old numeric ID
    if identifier != page.get_url_identifier():
        return redirect(url_for('admin.edit_page', identifier=page.get_url_identifier()), code=301)

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        slug = request.form.get('slug', '').strip().lower()
        content = request.form.get('content', '')
        location = request.form.get('location', 'footer')
        display_order = int(request.form.get('display_order', 0) or 0)
        is_published = request.form.get('is_published') == 'on'
        open_new_tab = request.form.get('open_new_tab') == 'on'

        # Validate
        if not title:
            flash(_l('Le titre est requis'), 'error')
            return render_template('admin/edit_page.html', page=page)

        # Generate slug if not provided
        if not slug:
            slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')

        # Check slug uniqueness (excluding current page)
        existing = Page.query.filter(Page.slug == slug, Page.id != page.id).first()
        if existing:
            flash(_l('Ce slug existe deja'), 'error')
            return render_template('admin/edit_page.html', page=page)

        # Validate slug format
        if not re.match(r'^[a-z0-9\-]+$', slug):
            flash(_l('Le slug ne peut contenir que des lettres minuscules, chiffres et tirets'), 'error')
            return render_template('admin/edit_page.html', page=page)

        page.title = title
        page.slug = slug
        page.content = content
        page.location = location
        page.display_order = display_order
        page.is_published = is_published
        page.open_new_tab = open_new_tab

        db.session.commit()

        flash(_l('Page modifiee avec succes'), 'success')
        return redirect(url_for('admin.pages'))

    return render_template('admin/edit_page.html', page=page)


@admin_bp.route('/pages/<identifier>/delete', methods=['POST'])
@login_required
@superadmin_required
def delete_page(identifier):
    """Delete a custom page."""
    from app.models.page import Page

    page = Page.get_by_identifier(identifier)
    if not page:
        flash(_l('Page introuvable'), 'error')
        return redirect(url_for('admin.pages'))
    db.session.delete(page)
    db.session.commit()

    flash(_l('Page supprimee avec succes'), 'success')
    return redirect(url_for('admin.pages'))


@admin_bp.route('/pages/<identifier>/preview')
@login_required
@superadmin_required
def preview_page(identifier):
    """Preview a page (even if not published)."""
    from app.models.page import Page

    page = Page.get_by_identifier(identifier)
    if not page:
        flash(_l('Page introuvable'), 'error')
        return redirect(url_for('admin.pages'))

    # Redirect if accessed by old numeric ID
    if identifier != page.get_url_identifier():
        return redirect(url_for('admin.preview_page', identifier=page.get_url_identifier()), code=301)
    return render_template('page/view.html', page=page, is_preview=True)
