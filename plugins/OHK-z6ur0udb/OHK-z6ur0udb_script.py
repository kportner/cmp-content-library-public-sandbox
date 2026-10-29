"""
This is a working sample CloudBolt plug-in for you to start with. The run method is required,
but you can change all the code within it. See the "CloudBolt Plug-ins" section of the docs for
more info and the CloudBolt forge for more examples:
https://github.com/CloudBoltSoftware/cloudbolt-forge/tree/master/actions/cloudbolt_plugins
"""
from common.methods import set_progress


def run(job, *args, **kwargs):
    server_hostname = '{{server_hostname}}'
    set_progress("This will show up in the job details page in the CB UI, and in the job log")

    # Example of how to fetch arguments passed to this plug-in ('server' will be available in
    # some cases)
    server = kwargs.get('server')
    if server:
        set_progress("This plug-in is running for server {}".format(server))

    set_progress("Dictionary of keyword args passed to this plug-in: {}".format(kwargs.items()))

    if True:
        # Each of these keys in the return dictionary is optional (if status is not included, it'll be treated as "SUCCESS")
        return {"status": "SUCCESS", "output_message": "Sample output message"}
    else:
        return {"status": "FAILURE", "output_message": "Sample output message", "error_message": "Sample error message, this is shown in red"}


def generate_options_for_server_hostname(field, **kwargs):
    """
    A working sample that returns a dynamically generated list of options.

    :param field: The field you are generating options for (of type CustomField or its subclass HookInput).

    See the "Generated Parameter Options" section of the docs for more info and the CloudBolt forge
    for more examples: https://github.com/CloudBoltSoftware/cloudbolt-forge/tree/master/actions/cloudbolt_plugins
    """

    # In the simple cases where the label shown to users is the same as the value to be saved,
    # return a simple list of values
    return [1, 10, 42, 100]

    # Otherwise, define the database values and labels as a list of 2-tuples.
    options = [
        (1, 'One'),
        (2, 'Two'),
        (3, 'Three'),
    ]

    return {
        'options': options,
    }