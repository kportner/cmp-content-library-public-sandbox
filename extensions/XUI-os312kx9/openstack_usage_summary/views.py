"""
OpenStack usage summary report using openstacksdk (TechnologyWrapper.connection).
"""
from extensions.views import report_extension, ReportExtensionDelegate
from django.shortcuts import render
from django.urls import reverse
from resourcehandlers.openstack.models import OpenStackHandler
from utilities.logger import ThreadLogger
import urllib.parse
import shutil
import os


logger = ThreadLogger(__name__)


def _nova_absolute_usage_dict(wrapper):
    abs_lim = wrapper.connection.compute.get_limits().absolute
    if abs_lim is None:
        return {}
    return {
        "maxTotalInstances": abs_lim.instances,
        "totalInstancesUsed": abs_lim.instances_used,
        "maxTotalCores": abs_lim.total_cores,
        "totalCoresUsed": abs_lim.total_cores_used,
        "maxTotalRAMSize": abs_lim.total_ram,
        "totalRAMUsed": abs_lim.total_ram_used,
        "maxTotalFloatingIps": abs_lim.floating_ips,
        "maxSecurityGroups": abs_lim.security_groups,
    }


def _volume_absolute_usage_dict(wrapper):
    abs_lim = wrapper.connection.block_storage.get_limits().absolute
    if abs_lim is None:
        return {}
    return {
        "maxTotalVolumes": abs_lim.max_total_volumes,
        "totalVolumesUsed": abs_lim.total_volumes_used,
        "maxTotalSnapshots": abs_lim.max_total_snapshots,
        "totalSnapshotsUsed": abs_lim.total_snapshots_used,
        "maxTotalVolumeGigabytes": abs_lim.max_total_volume_gigabytes,
        "totalGigabytesUsed": abs_lim.total_gigabytes_used,
    }


def _set_report_thumbnails():
    from settings import PROSERV_DIR

    dst_dir = os.path.join(PROSERV_DIR, "static", "openstack_usage_summary_312", "images")
    os.makedirs(dst_dir, exist_ok=True)
    src_dir = os.path.join(PROSERV_DIR, "xui/openstack_usage_summary_312/static/images")
    thumbnails = ["openstack_limit_summary.png"]
    for thumbnail in thumbnails:
        src = os.path.join(src_dir, thumbnail)
        dst = os.path.join(dst_dir, thumbnail)
        try:
            shutil.copyfile(src, dst)
        except OSError:
            logger.debug("Thumbnail copy skipped (missing %s)", src)


class OpenStackUsage312Delegate(ReportExtensionDelegate):
    def should_display(self):
        _set_report_thumbnails()
        return True


def usage_summary_data_helper(proj_id, proj_name, rh_id):
    """
    Collect OpenStack volume, compute and network summary by project id.
    """
    if rh_id:
        rh = OpenStackHandler.objects.get(id=rh_id)
    else:
        rh = OpenStackHandler.objects.last()
    projects = {}

    compute = {
        "Instances": {"total": 0, "used": 0},
        "VCPUs": {"total": 0, "used": 0},
        "RAM": {"total": 0, "used": 0},
    }
    volume = {
        "Volumes": {"total": 0, "used": 0},
        "Snapshots": {"total": 0, "used": 0},
        "Storage": {"total": 0, "used": 0},
    }
    network = {
        "FloatingIPs": {"total": 0, "used": 0},
        "SecurityGroups": {"total": 0, "used": 0},
        "SecurityGroupRules": {"total": 0, "used": 0},
    }
    handlers = {}
    for os_rh in OpenStackHandler.objects.all():
        handlers[str(os_rh.id)] = os_rh.name

    if rh:
        cmp_projects = [env.node_location for env in rh.environment_set.all()]
        if proj_id:
            connection_kwargs = rh.get_connection_kwargs()
            connection_kwargs["project_id"] = proj_id
            logger.info("connection kwargs: %s", connection_kwargs)
            rh.resource_technology.init(
                rh.ip,
                rh.port,
                rh.serviceaccount,
                rh.servicepasswd,
                rh.get_ssl_verification(),
                **connection_kwargs,
            )
            wrapper = rh.get_api_wrapper(proj_name)
        else:
            wrapper = rh.get_api_wrapper()
            proj_id = rh.project_id
            rh_id = str(rh.id)
        logger.info("Open Stack project id: %s", proj_id)

        ns_dict = _nova_absolute_usage_dict(wrapper)
        vs_dict = _volume_absolute_usage_dict(wrapper)
        logger.info("Open Stack compute summary: %s", ns_dict)
        logger.info("Open Stack volume summary: %s", vs_dict)

        if ns_dict:
            compute.update(
                {
                    "Instances": {
                        "total": ns_dict["maxTotalInstances"],
                        "used": ns_dict["totalInstancesUsed"],
                    },
                    "VCPUs": {
                        "total": ns_dict["maxTotalCores"],
                        "used": ns_dict["totalCoresUsed"],
                    },
                    "RAM": {
                        "total": (ns_dict.get("maxTotalRAMSize") or 0) / 1024,
                        "used": (ns_dict.get("totalRAMUsed") or 0) / 1024,
                    },
                }
            )

            total_floating_ips_used = len(list(wrapper.connection.network.ips()))
            total_security_groups_used = len(
                list(wrapper.connection.network.security_groups())
            )

            network.update(
                {
                    "FloatingIPs": {
                        "total": ns_dict["maxTotalFloatingIps"],
                        "used": total_floating_ips_used,
                    },
                    "SecurityGroups": {
                        "total": ns_dict["maxSecurityGroups"],
                        "used": total_security_groups_used,
                    },
                    "SecurityGroupRules": {"total": 100, "used": 0},
                    "Networks": {"total": 100, "used": 0},
                    "Ports": {"total": 500, "used": 0},
                    "Routers": {"total": 10, "used": 0},
                }
            )
        if vs_dict:
            volume.update(
                {
                    "Volumes": {
                        "total": vs_dict["maxTotalVolumes"],
                        "used": vs_dict["totalVolumesUsed"],
                    },
                    "Snapshots": {
                        "total": vs_dict["maxTotalSnapshots"],
                        "used": vs_dict["totalSnapshotsUsed"],
                    },
                    "Storage": {
                        "total": vs_dict["maxTotalVolumeGigabytes"],
                        "used": vs_dict["totalGigabytesUsed"],
                    },
                }
            )
        if proj_name:
            wrapper = rh.get_api_wrapper(proj_name)

            projects = {
                proj.id: proj.name
                for proj in wrapper.get_all_locations()
                if proj.name in cmp_projects
            }
        if not projects:
            connection_kwargs = rh.get_connection_kwargs()
            connection_kwargs["project_id"] = rh.project_id
            logger.info("connection kwargs: %s", connection_kwargs)
            rh.resource_technology.init(
                rh.ip,
                rh.port,
                rh.serviceaccount,
                rh.servicepasswd,
                rh.get_ssl_verification(),
                **connection_kwargs,
            )
            wrapper = rh.resource_technology.work_class

            projects = {
                proj.id: proj.name
                for proj in wrapper.get_all_locations()
                if proj.name in cmp_projects
            }

        logger.info("Open Stack projects: %s", projects)

    return (projects, network, compute, volume, proj_id, handlers, rh_id)


@report_extension(
    title="OpenStack Usage Summary",
    description="OpenStack limits and usage via openstacksdk (Python 3.12 compatible).",
    thumbnail="images/openstack_limit_summary.png",
    delegate=OpenStackUsage312Delegate,
)
def openstack_usage_summary_312(request):
    proj_id = request.GET.get("proj_id", None)
    proj_name = request.GET.get("proj_name", None)
    if proj_name:
        proj_name = urllib.parse.unquote(proj_name)
    rh_id = request.GET.get("rh_id", None)
    logger.info("request query params:%s", request.GET.dict())
    (
        projects,
        network,
        compute,
        volume,
        proj_id,
        handlers,
        rh_id,
    ) = usage_summary_data_helper(proj_id, proj_name, rh_id)

    logger.info(
        "summary data, network: %s, compute:%s, volume:%s",
        network,
        compute,
        volume,
    )

    return render(
        request,
        "openstack_usage_summary_312/reports/summary.html",
        dict(
            uplink={"url": reverse("report_list"), "label": "Reports"},
            pagetitle="OpenStack Limit Summary",
            report_slug="OpenStack-Usage-Summary-3.12",
            intro=""" """,
            volume=volume,
            network=network,
            compute=compute,
            projects=projects,
            proj_id=proj_id,
            handlers=handlers,
            rh_id=rh_id,
        ),
    )
