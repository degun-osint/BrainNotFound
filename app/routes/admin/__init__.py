"""Admin blueprint (/admin), one module per area; URLs and endpoint names are unchanged."""
from flask import Blueprint

admin_bp = Blueprint('admin', __name__)

# Importing the modules registers their routes on admin_bp
from app.routes.admin import (  # noqa: E402,F401
    common, dashboard, quizzes, results, groups, users, settings, pages,
)
