from django.urls import path
from core import views
from core import auth
from django.contrib.auth.views import LoginView


app_name = "core"

urlpatterns = [
    path('preferences/', views.user_preferences_update, name='user_preferences'),
    path('login/', LoginView.as_view(template_name='login.html'), name='login'),
    path('logout/', auth.user_logout, name="logout"),
    path('tst/', views.tst, name='tst'),
]
