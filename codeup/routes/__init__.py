from codeup.routes.ai_routes import ai_bp
from codeup.routes.core import core_bp
from codeup.routes.memory import memory_bp
from codeup.routes.projects import projects_bp
from codeup.routes.site import site_bp

ALL_BLUEPRINTS = [core_bp, site_bp, ai_bp, memory_bp, projects_bp]
