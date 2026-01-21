"""Custom pages model for site content."""
from datetime import datetime
from app import db


class Page(db.Model):
    """Custom page model for footer/menu content."""
    __tablename__ = 'pages'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(200), unique=True, nullable=False)
    content = db.Column(db.Text, nullable=False)  # Markdown content

    # Display location: 'menu', 'footer', 'both', 'none' (draft)
    location = db.Column(db.String(20), default='footer')

    # Order for display (lower = first)
    display_order = db.Column(db.Integer, default=0)

    # Publication status
    is_published = db.Column(db.Boolean, default=False)

    # Open in new tab
    open_new_tab = db.Column(db.Boolean, default=False)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<Page {self.title}>'

    @staticmethod
    def get_menu_pages():
        """Get all published pages for menu display."""
        return Page.query.filter(
            Page.is_published == True,
            Page.location.in_(['menu', 'both'])
        ).order_by(Page.display_order).all()

    @staticmethod
    def get_footer_pages():
        """Get all published pages for footer display."""
        return Page.query.filter(
            Page.is_published == True,
            Page.location.in_(['footer', 'both'])
        ).order_by(Page.display_order).all()

    def get_html_content(self):
        """Convert markdown content to HTML."""
        import markdown
        return markdown.markdown(
            self.content,
            extensions=['tables', 'fenced_code', 'nl2br']
        )
