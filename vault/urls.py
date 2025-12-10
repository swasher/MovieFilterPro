from django.urls import path
from vault import views

urlpatterns = [
    path('vault/', views.vault, name='vault'),
]