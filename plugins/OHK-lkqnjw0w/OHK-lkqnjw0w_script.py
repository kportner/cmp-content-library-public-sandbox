from common.methods import set_progress
import requests
import json
from utilities.models import ConnectionInfo


def run(job, *args, **kwargs):
    resource = kwargs.pop('resources').first()
    tf = ConnectionInfo.objects.get(name='Terraform Cloud')
    url = tf.protocol + "://" + tf.ip + "/api/v2/workspaces/" + resource.tf_workspace_id + "/actions/lock"

    payload = json.dumps({
        "reason": "Locked via CloudBolt"
    })

    headers = {
    'Content-Type': 'application/vnd.api+json',
    'Authorization': 'Bearer ' + tf.password
    }

    response = requests.request("POST", url, headers=headers, data=payload)
    resource.tf_workspace_lock = response.json()['data']['attributes']['locked']

    if True:
        return "SUCCESS", "Workspace Created.", ""
    else:
        return "FAILURE", "Something went wrong.", "Something went wrong."