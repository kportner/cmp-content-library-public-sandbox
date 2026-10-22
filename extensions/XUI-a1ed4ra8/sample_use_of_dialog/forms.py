from django import forms
from django.utils.translation import gettext as _, gettext_lazy as _lazy

from common.forms import C2Form
from infrastructure.models import CustomField, Namespace, Server
from utilities.logger import ThreadLogger

logger = ThreadLogger(__name__)


class ServerMessageForm(C2Form):
    server_id = forms.CharField(widget=forms.widgets.HiddenInput())
    message = forms.CharField(
        label=_lazy("Message"),
        max_length=256,
        widget=forms.widgets.Textarea(attrs={'rows': 5, 'cols': 80}),
        required=True,
    )

    def save(self, profile):
        server_id = self.cleaned_data['server_id']
        message = self.cleaned_data.get('message')
        server = Server.objects.get(id=server_id)

        sample_namespace, created = Namespace.objects.get_or_create(name='sample')
        if created:
            logger.debug("To add sample params without clutering the regular UI, "
                         "created 'sample' namespace")
        message_field, created = CustomField.objects.get_or_create(
            name="server_sample_message", type='TXT', label="Sample Message")
        if created:
            logger.debug("Created new 'server_sample_message' parameter")

        from orders.views import get_cfv
        server.custom_field_values.add(get_cfv(message_field, message))

        msg = _("Added a new sample message to '{server}'")

        return True, msg.format(server=server.hostname)
