"""
Discover Google Cloud Firewall Rules.
"""

import json

from common.methods import set_progress
from infrastructure.models import Environment
from resourcehandlers.gcp.models import GCPProject
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


RESOURCE_IDENTIFIER = "google_firewall_name"


def discover_resources(**kwargs):
    discovered_firewall_rules = []
    processed_projects = set()

    environments = Environment.objects.filter(
        resource_handler__resource_technology__name="Google Cloud Platform"
    )

    for environment in environments:

        try:
            rh = environment.resource_handler.cast()

            if not environment.gcp_project:
                set_progress(
                    f"Skipping environment '{environment.name}' because no GCP project is configured."
                )
                continue

            try:
                gcp_project = GCPProject.objects.get(id=environment.gcp_project)
            except GCPProject.DoesNotExist:
                set_progress(
                    f"GCPProject with id {environment.gcp_project} does not exist."
                )
                continue

            # Google Project ID (NOT display name)
            project = gcp_project.gcp_id

            # Skip duplicate projects
            if project in processed_projects:
                continue

            processed_projects.add(project)

            set_progress(f"Connecting to Google Cloud project '{project}'...")

            credentials = Credentials.from_authorized_user_info(
                json.loads(rh.gcp_api_credentials)
            )

            compute = build(
                "compute",
                "v1",
                credentials=credentials,
                cache_discovery=False,
            )

            request = compute.firewalls().list(project=project)

            firewall_count = 0

            while request is not None:

                response = request.execute()

                for rule in response.get("items", []):

                    discovered_firewall_rules.append(
                        {
                            "name": rule["name"],
                            "google_firewall_name": rule["name"],
                            "google_firewall_priority": rule.get("priority"),
                            "google_firewall_direction": rule.get("direction"),
                            "google_cloud_project": project,
                            "google_rh_id": rh.id,
                        }
                    )

                    firewall_count += 1

                request = compute.firewalls().list_next(
                    previous_request=request,
                    previous_response=response,
                )

            set_progress(
                f"Discovered {firewall_count} firewall rule(s) in project '{project}'."
            )

        except HttpError as e:
            set_progress(
                f"Failed to discover firewall rules for project '{project}': {e}"
            )

        except Exception as e:
            set_progress(
                f"Unexpected error while discovering project '{project}': {e}"
            )

    return discovered_firewall_rules