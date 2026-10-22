from django import forms


class MFAForm(forms.Form):
    def __init__(self, *args, **kwargs):
        self.force = kwargs.pop("force", False)
        self.mfa_enforcement = kwargs.pop("mfa", "Enforce")
        super().__init__(*args, **kwargs)
        
    def save(self, profiles):
        set_counter = 0
        skipped_counter = 0
        plural = "s"
        for profile in profiles:
            if (
                not self.force and
                not self.mfa_enforcement == "Inactive" and
                profile.mfa_enabled in ["Active", "Enforce"]
            ):
                skipped_counter += 1
                continue
            profile.mfa_enabled = self.mfa_enforcement
            profile.mfa_totp_secret = None
            profile.save()
            set_counter += 1
            
        if set_counter == 1:
            plural = ""
        msg = f"Set MFA to '{self.mfa_enforcement}' for {set_counter} user{plural}!"

        if skipped_counter > 0:
            msg += f" {skipped_counter} users already had MFA enabled."
        return msg
