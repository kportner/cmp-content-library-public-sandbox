from django.shortcuts import render
from datetime import datetime, timedelta

from extensions.views import dashboard_extension
from accounts.models import UserProfile


@dashboard_extension(
    title="Logged-in Users", description="Users logged into the system"
)
def loggedin_users_widget(request):

    logged_in_users = UserProfile.objects.filter(
        last_activity_time__gte=datetime.now() - timedelta(minutes=5)
    )
    return render(
        request,
        template_name="io_cloudbolt_users_widget/templates/loggedin_users.html",
        context={"users": logged_in_users},
    )
