"""//docs.microsoft.com/en-us/rest/api/azure/devops/pipelines/runs/run
This is a blueprint action built for Rockwell
This action will connect to Azure DevOps and run a Pipeline
Requirements:
    Configured Personal Access Token (PAT) in Azure DevOps:
        https://docs.microsoft.com/en-us/azure/devops/organizations/accounts/use-personal-access-tokens-to-authenticate?view=azure-devops&tabs=preview-page
    Configured ConnectionInfo with the following information:
        Name: {devops org}
        IP: https://dev.azure.com/{organization name}
        username: PAT name
        password: PAT token
Relevant links:
    https://docs.microsoft.com/en-us/rest/api/azure/devops/?view=azure-devops-rest-6.1
    https://docs.microsoft.com/en-us/rest/api/azure/devops/pipelines/runs/run%20pipeline?view=azure-devops-rest-6.1
Created By: Bryce Swarm (CloudBolt Software, bswarm@cloudbolt.io)
"""
import json

from common.methods import set_progress
from utilities.models import ConnectionInfo
import requests
import time

# Replace this with your Connection Info name
# CI_NAME = "Azure DevOps"
CI_NAME = "JB ADO"


def _run(method, url, body=None, headers=None):
    # creds
    creds = ConnectionInfo.objects.get(name=CI_NAME)
    auth = (creds.username, creds.password)
    headers = {"Content-Type": "application/json"}
    url = creds.ip + url

    response = requests.request(method, url, json=body, headers=headers,
                                auth=auth)
    if response.status_code not in [200, 201, 204]:
        if response.status_code == 401:
            raise Exception("Unable to connect using the information provided")
        elif response.status_code == 403:
            raise Exception("Forbidden call, user does not have permission")
        raise Exception(
            "Azure return code: {}, response text: {}s".format(
                response.status_code, response.text
            )
        )

    return response


def generate_options_for_project(*args, **kwargs):
    projects = []
    url = "/_apis/projects"
    response = _run(method="GET", url=url)
    response = response.json()
    for project in response["value"]:
        projects.append(project["name"])

    return projects


def generate_options_for_pipeline(control_value=None, *args, **kwargs):
    pipelines = []
    if control_value:
        url = f"/{control_value}/_apis/pipelines?api-version=6.1-preview.1"
        response = _run(method="GET", url=url)
        response = response.json()
        for pipeline in response["value"]:
            pipelines.append((pipeline["id"], pipeline["name"]))
    return pipelines


def wait_for_completion(project_id, pipeline_id, run_id, run_state):
    """
    run_id:         int:
    pipeline_id:    int:
    state:          str: inProgress, etc..
    """
    # List of valid "pending" states that ADO will return
    PENDING_LIST = ['inProgress']

    while run_state in PENDING_LIST:
        url = f"/{project_id}/_apis/pipelines/{int(pipeline_id)}/runs/{int(run_id)}?api-version=6.1-preview.1"
        response = _run(method="GET", url=url)
        j_response = response.json()
        run_state = j_response["state"]
        time.sleep(15)
        set_progress(f'Status: {run_state}, waiting 15 seconds...')

    return run_state


def run(job, *args, **kwargs):
    project = "{{ project }}"
    pipeline = "{{ pipeline }}"
    branch = "{{ branch }}"

    body = {
        "resources": {
            "repositories": {"self": {"refName": f"refs/heads/{branch}"}}}
    }
    url = f"/{project}/_apis/pipelines/{int(pipeline)}/runs?api-version=6.1-preview.1"
    response = _run(method="POST", url=url, body=body)

    # Example response json:
    #
    # {'_links': {'self': {'href': 'https://dev.azure.com/bswarm/6937c0f0-dddf-4186-90de-bef80e73425a/_apis/pipelines/1/runs/7'},
    #       'web': {'href': 'https://dev.azure.com/bswarm/6937c0f0-dddf-4186-90de-bef80e73425a/_build/results?buildId=7'},
    #       'pipeline.web': {'href': 'https://dev.azure.com/bswarm/6937c0f0-dddf-4186-90de-bef80e73425a/_build/definition?definitionId=1'},
    #       'pipeline': {'href': 'https://dev.azure.com/bswarm/6937c0f0-dddf-4186-90de-bef80e73425a/_apis/pipelines/1?revision=1'}},
    #       'pipeline': {
    #           'url': 'https://dev.azure.com/bswarm/6937c0f0-dddf-4186-90de-bef80e73425a/_apis/pipelines/1?revision=1',
    #           'id': 1,
    #           'revision': 1,
    #           'name': 'bryceswarm.python-sample-vscode-flask-tutorial',
    #           'folder': '\\'},
    #       'state': 'inProgress',
    #       'createdDate': '2021-07-15T22:52:55.7508045Z',
    #       'url': 'https://dev.azure.com/bswarm/6937c0f0-dddf-4186-90de-bef80e73425a/_apis/pipelines/1/runs/7',
    #       'resources': {
    #           'repositories': {
    #               'self': {
    #                   'repository': {
    #                       'fullName': 'bryceswarm/python-sample-vscode-flask-tutorial',
    #                       'connection': {'id': 'b8cd63cf-ddd1-4cd7-a3d6-5840797b82a6'},
    #                       'type': 'gitHub'},
    #               'refName': 'refs/heads/master',
    #               'version': 'bed19241f5f14712d5077d0a6bc56624938487b9'}}},
    #   'id': 7,
    #   'name': '20210715.6'}

    j_response = response.json()
    build_id = int(j_response['id'])
    set_progress(
        f'Run {j_response["name"]} started with ID: {j_response["id"]}')
    set_progress(
        f'Status: {j_response["state"]}')
    state = wait_for_completion(project, pipeline, j_response["id"],
                                j_response["state"])

    msg = ""

    if state == "completed":
        # Fetch build result
        url = f"/{project}/_apis/build/Builds/{build_id}"
        response = _run(method="GET", url=url)
        j_response = response.json()
        build_result = j_response.get('result')

        # Fetch build timeline
        url = f"/{project}/_apis/build/builds/{build_id}/Timeline"
        response = _run(method="GET", url=url)
        j_response = response.json()
        for record in j_response.get("records", []):
            if "issues" in record:
                for issue in record.get("issues", []):
                    msg += f"{issue['type']}: {issue['message']}\n"

        if build_result == "failed":
            return "FAILURE", "", msg

    return "SUCCESS", "", f"{state}"
