ALLOWED_XUI_EXTENSIONS = [".py", ".html", ".png"]

# If the parameter required for the extension does not exist, create it with the default value.
from infrastructure.models import CustomField

CustomField.objects.get_or_create(
    name="mfa_enabled",
    defaults={
        "label": "MFA Enabled",
        "type": "STR",
        "description": "Enable MFA for this user.",
        "show_as_attribute": True,
    },
)
CustomField.objects.get_or_create(
    name="mfa_totp_secret",
    defaults={
        "label": "MFA Secret",
        "type": "PWD",
        "description": "MFA User Secret.",
        "show_as_attribute": False,
    },
)
