from django.urls import path
from core import views

# app_name = "core"

urlpatterns = [
    path('preferences/', views.user_preferences_update, name='user_preferences'),
]