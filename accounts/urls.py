from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.MaderLoginView.as_view(), name="login"),
    path("logout/", views.MaderLogoutView.as_view(), name="logout"),
    path("password/change/", views.password_change, name="password_change"),
    path("password/change/done/", views.password_change_done, name="password_change_done"),
    path("profile/", views.profile, name="profile"),
]
