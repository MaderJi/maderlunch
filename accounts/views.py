from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import redirect, render
from django.urls import reverse_lazy

from audit.services import log_event

from .forms import StyledAuthenticationForm, StyledPasswordChangeForm


class MaderLoginView(LoginView):
    template_name = "registration/login.html"
    form_class = StyledAuthenticationForm
    redirect_authenticated_user = True


class MaderLogoutView(LogoutView):
    next_page = reverse_lazy("accounts:login")


@login_required
def password_change(request):
    if request.method == "POST":
        form = StyledPasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            profile = getattr(user, "profile", None)
            if profile and profile.must_change_password:
                profile.must_change_password = False
                profile.save(update_fields=["must_change_password"])
            log_event(request, "user.password_change_self", target=user)
            return redirect("accounts:password_change_done")
    else:
        form = StyledPasswordChangeForm(request.user)
    return render(request, "accounts/password_change.html", {"form": form})


@login_required
def password_change_done(request):
    return render(request, "accounts/password_change_done.html")


@login_required
def profile(request):
    return render(request, "accounts/profile.html", {"profile": getattr(request.user, "profile", None)})
