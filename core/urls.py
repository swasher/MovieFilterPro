from django.urls import path
from core import api_auth


app_name = "core"

urlpatterns = [
    path('api/auth/session/', api_auth.session_view, name='api_auth_session'),
    path('api/auth/login/', api_auth.login_view, name='api_auth_login'),
    path('api/auth/logout/', api_auth.logout_view, name='api_auth_logout'),
]
