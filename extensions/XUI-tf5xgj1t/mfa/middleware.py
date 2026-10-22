from django.shortcuts import resolve_url
from django.urls import reverse
from django.utils.deprecation import MiddlewareMixin
from django.contrib.auth import REDIRECT_FIELD_NAME as redirect_field_name
from django.contrib.auth.views import redirect_to_login
from xui.mfa.views import is_mfa_enabled


class MfaMiddleware(MiddlewareMixin):
    def process_request(self, request):

        # once the user is authenticated and if they haven't come in via a trusted saml2 identity then setup mfa
        if (
            request.user.is_authenticated
            and request.session['_auth_user_backend'] != 'authentication.sso.backends.Saml2Backend'
            and request.path != "/accounts/logout/"
            and request.path != "/quick_setup/"
            and request.path != "/_/features/"
            and request.path != "/portal.css"
            and not request.path.startswith("/api/")
            and request.path != "/product_license/eula/"
            and request.path != "/accounts/password/setchallenge/"
            and not request.path.startswith("/static")
            and request.method != "POST"
            and not request.path.startswith("/__debug__")
        ):

            """
            If the user does not have an MFA configured, redirect to the MFA setup page
            """

            if (
                is_mfa_enabled(request) == "Enforce"
                and request.path != reverse("configure_mfa")
                and request.path != reverse("mfa_qr_code")
                and request.path != reverse("verify_second_factor_totp")
            ):

                current_path = request.path
                paths = [reverse("configure_mfa")]

                if current_path not in paths:
                    path = request.get_full_path()

                    resolved_login_url = resolve_url(reverse("configure_mfa"))

                    return redirect_to_login(
                        path, resolved_login_url, redirect_field_name
                    )
            elif (
                is_mfa_enabled(request) == "Active"
                and not request.session.get("verified_mfa")
                and request.path != reverse("configure_mfa")
            ):
                """
                If the user has an MFA configured, redirect to the MFA verification page
                """

                current_path = request.path
                paths = [reverse("verify_second_factor_totp")]
                if current_path not in paths:
                    path = request.get_full_path()
                    resolved_login_url = resolve_url(
                        reverse("verify_second_factor_totp")
                    )

                    return redirect_to_login(
                        path, resolved_login_url, redirect_field_name
                    )
