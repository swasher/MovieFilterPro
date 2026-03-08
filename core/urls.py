from django.urls import path
from core import views
from core import auth
from core import api_auth
from django.contrib.auth.views import LoginView


app_name = "core"

urlpatterns = [
    path('api/auth/session/', api_auth.session_view, name='api_auth_session'),
    path('api/auth/login/', api_auth.login_view, name='api_auth_login'),
    path('api/auth/logout/', api_auth.logout_view, name='api_auth_logout'),
    path('preferences/', views.user_preferences_update, name='user_preferences'),
    path('login/', LoginView.as_view(template_name='login.html'), name='login'),
    path('logout/', auth.user_logout, name="logout"),
    path('tst/', views.tst, name='tst'),
    path('register/', auth.register_user, name='register'),
    path('delete_account/', auth.delete_account, name='delete_account'),
]
