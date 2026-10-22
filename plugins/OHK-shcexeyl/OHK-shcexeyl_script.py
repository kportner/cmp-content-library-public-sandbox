"""
Server Action to extend the expiration date of a Server by 30 days and notify
Approvers in the Server's Group.
"""

import datetime

from utilities.logger import ThreadLogger
from utilities.mail import email
from utilities.exceptions import InvalidConfigurationException

logger = ThreadLogger(__name__)


def run(job, logger=None):
    # Extend Server Expiration Date
    server = job.server_set.first()

    if not server:
        return "", "No server found for this job.", ""

    # If the server doesn't have an expiration date, quit without assigning one.
    if server.expiration_date is None:
        return "", "This server does not have an expiration date.", ""

    new_date = server.expiration_date + datetime.timedelta(days=30)
    server.set_value_for_custom_field("expiration_date", new_date)

    # Notify Approvers
    email_addrs = [
        approver.user.email
        for approver in server.group.get_approvers()
        if approver.user and approver.user.email
    ]
   
    if not email_addrs:
        return "", "No approver email addresses found.", ""

    subject = "CloudBolt: Server expiration extended by 30 days"

    message = (
        f"{job.owner} has extended the expiration date for "
        f"{server.hostname} by 30 days.\n\n"
        f"New expiration date: {new_date}"
    )

    email_context = {
        "subject": subject,
        "message": message,
    }

    try:
        email(
            recipients=email_addrs,
            context=email_context,
        )
    except InvalidConfigurationException:
        (logger or ThreadLogger(__name__)).warning(
            "Cannot connect to email (SMTP) server."
        )

    return "", "", ""
