"""
Sample tab extension views.

One @tab_extension is registered per supported model.  Each view fetches the
relevant object and renders a simple template.
"""
from django.shortcuts import get_object_or_404, render

from accounts.models import Group, UserProfile
from extensions.views import tab_extension, TabExtensionDelegate
from infrastructure.models import Environment, Server
from resourcehandlers.models import ResourceHandler
from resources.models import Resource
from servicecatalog.models import ServiceBlueprint

TEMPLATE = "sample/templates/tab-sample.html"


class AlwaysHideDelegate(TabExtensionDelegate):
    def should_display(self) -> bool:
        return False


class AlwaysShowDelegate(TabExtensionDelegate):
    def should_display(self) -> bool:
        return True


# @tab_extension(model=Server, title="Sample", description="My sample", delegate=AlwaysShowDelegate, replaces="history", hide_ootb_tab=True)
# def sample_server_tab(request, obj_id):
#     return render(request, TEMPLATE, {"label": "Server", "obj": get_object_or_404(Server, pk=obj_id)})


# @tab_extension(model=Environment, title="Sample", description="My sample", delegate=AlwaysShowDelegate, replaces="history", hide_ootb_tab=False)
# def sample_environment_tab(request, obj_id):
#     return render(request, TEMPLATE, {"label": "Environment", "obj": get_object_or_404(Environment, pk=obj_id)})


# @tab_extension(model=Group, title="Sample", description="My sample", delegate=AlwaysShowDelegate, replaces="history", hide_ootb_tab=False)
# def sample_group_tab(request, obj_id):
#     return render(request, TEMPLATE, {"label": "Group", "obj": get_object_or_404(Group, pk=obj_id)})


# @tab_extension(model=UserProfile, title="Sample", description="My sample", delegate=AlwaysShowDelegate, replaces="history", hide_ootb_tab=False)
# def sample_user_tab(request, obj_id):
#     return render(request, TEMPLATE, {"label": "User", "obj": get_object_or_404(UserProfile, pk=obj_id)})


# @tab_extension(model=ResourceHandler, title="Sample", description="My sample", delegate=AlwaysShowDelegate, replaces="history", hide_ootb_tab=False)
# def sample_resourcehandler_tab(request, obj_id):
#     return render(request, TEMPLATE, {"label": "Resource Handler", "obj": get_object_or_404(ResourceHandler, pk=obj_id)})


# @tab_extension(model=ServiceBlueprint, title="Sample", description="My sample", delegate=AlwaysShowDelegate, replaces="history", hide_ootb_tab=False)
# def sample_blueprint_tab(request, obj_id):
#     return render(request, TEMPLATE, {"label": "Blueprint", "obj": get_object_or_404(ServiceBlueprint, pk=obj_id)})


# @tab_extension(model=Resource, title="Sample", description="My sample", delegate=AlwaysShowDelegate, replaces="history", hide_ootb_tab=False)
# def sample_resource_tab(request, obj_id):
#     return render(request, TEMPLATE, {"label": "Resource", "obj": get_object_or_404(Resource, pk=obj_id)})