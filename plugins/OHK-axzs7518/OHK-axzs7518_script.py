import requests
from django.core.files.base import ContentFile

from common.methods import set_progress
from servicecatalog.models import ServiceBlueprint


def run(**kwargs):
    total_tasks = ServiceBlueprint.objects.filter(list_image='').count()
    set_progress(f"Found {total_tasks} BPs without an image", total_tasks=total_tasks)
    for i, bp in enumerate(ServiceBlueprint.objects.filter(list_image='')):
        set_progress(f"Working on BP {bp.name} ({i+1}/{total_tasks})", tasks_done=i)
        resp = requests.get('http://thecatapi.com/api/images/get', stream=True)
        bp.list_image.save(name='cat-{}.jpg'.format(bp.id), 
                           content=ContentFile(resp.content))