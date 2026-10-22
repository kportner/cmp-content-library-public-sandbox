#!/bin/env python

import os
from utilities.mail import email

def create_temp_file(basename, contents):
    tempfile_path = os.path.join("/tmp", basename)

    with open(tempfile_path, "w") as fd:
        fd.write(contents)

    return tempfile_path


def run(Job, server, **kwargs):
    remote_file = "{{ remote_file }}".strip()
    recipients = "{{comma_delimmited_recipients}}"

    file_contents = server.execute_script(
        script_contents='cat "{}"'.format(remote_file)
    )

    file_basename = os.path.basename(remote_file)

    addresses = [r.strip() for r in recipients.split(",") if r.strip()]

    subject = "Remote file from server {}".format(server)

    body = (
        "Please find attached file '{}' from server '{}', "
        "compliments of CloudBolt!"
    ).format(file_basename, server)

    mime_type = "text/plain"
    if file_basename.endswith((".html", ".htm")):
        mime_type = "text/html"
    elif file_basename.endswith(".csv"):
        mime_type = "text/csv"

    remote_file_path = create_temp_file(
        file_basename,
        file_contents
    )

    email_context = {
        "subject": subject,
        "message": body,
    }

    try:
        email(
            recipients=addresses,
            context=email_context,
            attachments=[(remote_file_path, mime_type)],
        )
    finally:
        if os.path.exists(remote_file_path):
            os.remove(remote_file_path)

    return "", "", ""
