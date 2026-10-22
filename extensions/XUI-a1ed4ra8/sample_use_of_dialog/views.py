from django.contrib import messages
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext as _

from extensions.views import tab_extension, TabExtensionDelegate
from infrastructure.models import Server
from orders.models import CustomFieldValue
from utilities.decorators import dialog_view

from .forms import ServerMessageForm


class ServerDialogSampleTabDelegate(TabExtensionDelegate):
    def should_display(self):
        return True


@dialog_view
def add_sample_message(request, server_id):

    server = Server.objects.get(id=server_id)

    if request.method == 'POST':
        profile = request.get_user_profile()
        form = ServerMessageForm(request.POST)

        if form.is_valid():
            success, msg = form.save(profile)
            if success:
                messages.success(request, msg)
            else:
                messages.warning(request, msg)
            return HttpResponseRedirect(
                reverse('server_detail', args=[server.id]))

    else:
        form = ServerMessageForm(initial={'server_id': server.id})

    return {
        'use_ajax': True,
        'form': form,
        'action_url': '/add_sample_message/{s_id}/'.format(s_id=server.id),
        'submit': _("Add Message")
    }


@dialog_view
def delete_sample_message(request, server_id, message_id):

    server = Server.objects.get(id=server_id)
    message = CustomFieldValue.objects.get(id=message_id)

    if request.method == 'POST':
        server.custom_field_values.remove(message)
        msg = _("Sample message deleted from server '{server}'")
        messages.info(request, msg.format(server=server.hostname))
        return HttpResponseRedirect(reverse('server_detail', args=[server.id]))

    else:
        content = _("Are you sure you want to delete '{msg}'?").format(msg=message.display_value)

        return {
            'title': _("Delete message?"),
            'content': content,
            'use_ajax': True,
            'action_url': "/delete_sample_message/{s_id}/message/{m_id}/".format(
                s_id=server_id, m_id=message_id),
            'submit': _("Delete"),
        }


@tab_extension(model=Server, title='Dialog Sample', delegate=ServerDialogSampleTabDelegate)
def dialog_sample_tab(request, obj_id):
    server = Server.objects.get(id=obj_id)

    messages = server.custom_field_values.filter(field__name="server_sample_message")

    return render(request, 'sample_use_of_dialog/templates/sample_tab.html', dict(
        server=server, messages=messages
    ))
