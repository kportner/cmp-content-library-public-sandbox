from common.methods import set_progress
from infrastructure.models import CustomField
from servicecatalog.models import ServiceBlueprint
from resources.models import Resource
from accounts.models import Group
from containerorchestrators.openshifthandler.models import Openshift

RESOURCE_IDENTIFIER = "openshift_project_name"


def get_or_create_custom_fields():
    CustomField.objects.get_or_create(
        name="openshift_project_name",
        label="Openshift Project Name",
        defaults={"type": "STR", "show_as_attribute": True},
    )
    CustomField.objects.get_or_create(
        name="openshift_project_id",
        label="Openshift Project ID",
        defaults={"type": "INT", "show_as_attribute": True},
    )


def discover_resources(**kwargs):
    # get or create custom fields if needed
    get_or_create_custom_fields()

    oc_handlers = Openshift.objects.all()
    created = 0
    updated = 0
    bp = ServiceBlueprint.objects.filter(name__iexact="OpenShift Project").first()
    group = Group.objects.filter(name__icontains="unassigned").first()

    for oc_handler in oc_handlers:
        total_created, total_updated, _, _ = oc_handler.sync_resource_metadata(
            sync_resource_type="sync_namespaces"
        )

        projects = total_created + total_updated

        for project in projects:
            project = project.cast()

            set_progress(f"Found {project.name}")

            # get project resource object
            resource = Resource.objects.filter(
                name=project.name, lifecycle="ACTIVE"
            ).first()
            if not resource:
                resource = Resource.objects.create(
                    name=project.name,
                    blueprint=bp,
                    group=group,
                    resource_type=bp.resource_type,
                    lifecycle="ACTIVE",
                )
                set_progress(f"Creating new resource {project.name}")
                created += 1
            else:
                updated += 1

            resource.openshift_project_id = project.id
            resource.openshift_project_name = project.name
            resource.lifecycle = "ACTIVE"
            resource.save()

    set_progress(
        f"OpenShift Project BP discovered {created + updated} resources where {created} created and {updated} updated."
    )

    return []