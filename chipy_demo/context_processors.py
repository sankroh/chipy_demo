from django.conf import settings
from datetime import date

def extra_context(request):     
    return {
        'static_url': settings.STATIC_URL,
        'today': date.today(),
    }