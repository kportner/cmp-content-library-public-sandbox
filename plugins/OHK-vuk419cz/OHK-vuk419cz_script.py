#!/usr/bin/env python
"""
Agent Telemetry Collection.
"""

if __name__ == "__main__":
    import django

    django.setup()

from datetime import datetime, timezone

from django.conf import settings

from common.methods import set_progress
from resourcehandlers.models import ResourceHandler
from resourcehandlers.utilization import (
    # AcropolisSamplingPeriods,
    # OpenStackSamplingPeriods,
    VMwareSamplingPeriods,
)
from satellite.models import MiraClient
from utilities.logger import ThreadLogger

logger = ThreadLogger(__name__)

TELEMETRY_MAPPING = {
    "vmware": VMwareSamplingPeriods,
    # "openstack": OpenStackSamplingPeriods,
    # "acropolis": AcropolisSamplingPeriods,
}


def post_to_cb_platform(telemetry_dict, file_name):
    """
    Upload a telemetry dictionary to the CB Platform as a JSON file.

    Serializes ``telemetry_dict`` and uploads it via the first available
    MiraClient. Any exception raised during upload is logged and suppressed.

    Args:
        telemetry_dict (dict): The telemetry payload to upload.
        file_name (str): The name to give the uploaded JSON file.

    Returns:
        bool: True if the upload succeeded, False otherwise.
    """
    client = MiraClient.objects.first()
    try:
        set_progress(
            f"Uploading telemetry data to CB Platform at {telemetry_dict['metadata']['upload_path']}"
        )
        client.upload_dict_as_json(telemetry_dict, file_name)
        return True
    except Exception as e:
        # something went wrong
        set_progress(e)
        logger.exception(e)
        return False


def adjust_usage_data(usage_data, cloud_type, samples):
    """
    Adjust usage data dictionary so there are always values and all values are floats.
    """
    transformed_usage_data = []
    for vm_usage_dict in usage_data:
        if len(vm_usage_dict.keys()) == 1:
            # this means there is no usage for the vm in the period,
            # skip it
            continue
        converted_dict = {}
        for key, value in vm_usage_dict.items():
            if key in ["mem_usage_values", "cpu_usage_values"]:
                float_values = [v * 1.0 for v in value]
                converted_dict[key] = float_values

            elif key == "resource_id":
                converted_dict[key] = value
        transformed_usage_data.append(converted_dict)
    return transformed_usage_data


def run(job, logger=None, **kwargs):
    """
    Collect VM usage telemetry for supported resource handlers and upload it.

    For each ResourceHandler whose ``type_slug`` is present in
    ``TELEMETRY_MAPPING``, gathers the last hour of CPU/memory usage for its
    active servers, normalizes the values, wraps them in a versioned telemetry
    payload, and posts each payload to the CB Platform. Exits early if no
    MiraClient is configured.

    :return: 3-tuple of (status, message, errors).
    """
    client = MiraClient.objects.first()
    if not client:
        set_progress("No MiraClient found. Exiting.")
        return "SUCCESS", "No MiraClient found, nothing to do.", ""

    now = datetime.now(timezone.utc)
    hour_dt = now.replace(minute=0, second=0, microsecond=0)

    for rh in ResourceHandler.objects.all():
        if rh.type_slug not in TELEMETRY_MAPPING.keys():
            continue

        sampling_period = TELEMETRY_MAPPING[rh.type_slug].last_hour

        usage = rh.cast().get_usage_for_vms(
            rh.server_set.filter(status="ACTIVE"),
            sampling_period.interval,
            sampling_period.samples,
            include_uuids=True,
        )
        usage = adjust_usage_data(usage, rh.type_slug, sampling_period.samples)

        telemetry_dict = {
            "version": "2025-05-12",
            "metadata": {
                "create_date": now.isoformat(),
                "agent_id": settings.UNIQUE_TOKEN,
                "upload_path": f"{rh.type_slug}/{rh.uuid}/usage/",
                "resource_handler_id": f"{rh.uuid}",
                "cloud_type": rh.type_slug,
                "sample_end_date": hour_dt.isoformat(),
                "sample_interval": sampling_period.interval,
            },
            "items": usage,
        }

        set_progress(f"Telemetry data for {rh.type_slug} {rh.uuid}: {telemetry_dict}")

        post_to_cb_platform(telemetry_dict, file_name="usage.json")

    return "SUCCESS", "Usage collection complete", ""
