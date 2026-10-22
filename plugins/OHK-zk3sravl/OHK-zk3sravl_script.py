"""
Teardown service for google firewall rules.
"""

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from resourcehandlers.gcp.models import GCPHandler
from common.methods import set_progress
import time, json


def run(job, logger=None, **kwargs):
    resource = kwargs.pop('resources').first()

    google_firewall_name = resource.attributes.get(field__name='google_firewall_name').value
    rh_id = resource.attributes.get(field__name='google_rh_id').value
    rh = GCPHandler.objects.get(id=rh_id).cast()
    project = resource.attributes.get(field__name='google_cloud_project').value

    set_progress('Connecting to Google Cloud')
    
    credentials = Credentials.from_authorized_user_info(
        json.loads(rh.gcp_api_credentials)
    )

    client = build('compute', 'v1', credentials=credentials)
    set_progress("Connection to google cloud established")

    set_progress('Deleting firewall rule %s...' % google_firewall_name)

    #delete the firewall
    client.firewalls().delete(project=project, firewall=google_firewall_name).execute()

    return "SUCCESS", "The firewall has been deleted", ""