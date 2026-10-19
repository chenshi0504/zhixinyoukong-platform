"""
WSGI config for sumo_simulation project.
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sumo_simulation.settings')

application = get_wsgi_application()