def get_options_list(field, **kwargs):
    """
    A working sample that returns a dynamically generated list of options.

    :param field: The field you are generating options for (of type CustomField or its subclass HookInput).

    See the "Generated Parameter Options" section of the docs for more info and the CloudBolt forge
    for more examples: https://github.com/CloudBoltSoftware/cloudbolt-forge/tree/master/actions/cloudbolt_plugins
    """

    # Otherwise, define the database values and labels as a list of 2-tuples.
    options = [
        (4, 'Four'),
        (5, 'Five'),
        (6, 'Six'),
    ]

    return {
        'options': options,
        'initial_value': 5,
        'sort': True,
        'override': False,
    }