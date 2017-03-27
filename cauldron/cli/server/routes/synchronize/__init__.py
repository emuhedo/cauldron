import json
import os
import tempfile
import flask
import mimetypes

import cauldron as cd
from cauldron.cli import sync
from cauldron.cli.commands.open import opener as project_opener
from cauldron.cli.server import arguments
from cauldron.cli.server import run as server_runner
from cauldron.cli.server.routes.synchronize import status
from cauldron.environ.response import Response


sync_status = dict(
    time=-1,
    project=None
)


@server_runner.APPLICATION.route('/sync-status', methods=['GET', 'POST'])
def fetch_synchronize_status():
    """
    Returns the synchronization status information for the currently opened
    project
    """

    r = Response()
    project = cd.project.internal_project

    if not project:
        r.fail(
            code='NO_PROJECT',
            message='No open project on which to retrieve status'
        )
    else:
        result = status.of_project(project)
        r.update(
            sync_time=sync_status.get('time', 0),
            source_directory=project.source_directory,
            remote_source_directory=project.remote_source_directory,
            status=result
        )

    return r.flask_serialize()


@server_runner.APPLICATION.route('/sync-open', methods=['POST'])
def sync_open_project():
    """ """

    r = Response()
    args = arguments.from_request()
    definition = args.get('definition')
    source_directory = args.get('source_directory')

    if None in [definition, source_directory]:
        return r.fail(
            code='INVALID_ARGS',
            message='Invalid arguments. Unable to open project'
        ).response.flask_serialize()

    # Remove any shared library folders from the library list. These will be
    # stored using the single shared library folder instead
    definition['library_folders'] = [
        lf
        for lf in definition.get('library_folders', ['libs'])
        if lf and not lf.startswith('..')
    ]
    definition['library_folders'] += ['../shared_libs']

    container_folder = tempfile.mkdtemp(prefix='cd-remote-project-')
    os.makedirs(os.path.join(container_folder, 'shared_libs'))
    os.makedirs(os.path.join(container_folder, 'downloads'))

    project_folder = os.path.join(container_folder, 'project')
    os.makedirs(project_folder)

    definition_path = os.path.join(project_folder, 'cauldron.json')
    with open(definition_path, 'w') as f:
        json.dump(definition, f)

    sync_status.update(time=-1, project=None)

    open_response = project_opener.open_project(project_folder, forget=True)
    project = cd.project.internal_project
    project.remote_source_directory = source_directory

    sync_status.update(time=-1, project=project)

    return r.consume(open_response).update(
        source_directory=project.source_directory
    ).notify(
        kind='SUCCESS',
        code='PROJECT_OPENED',
        message='Project opened'
    ).response.flask_serialize()


@server_runner.APPLICATION.route('/sync-file', methods=['POST'])
def sync_source_file():
    """ """

    r = Response()
    args = arguments.from_request()
    relative_path = args.get('relative_path')
    chunk = args.get('chunk')
    file_type = args.get('type')
    index = args.get('index', 0)
    sync_time = args.get('sync_time', 0)

    if None in [relative_path, chunk]:
        return r.fail(
            code='INVALID_ARGS',
            message='Missing or invalid arguments'
        ).response.flask_serialize()

    project = cd.project.internal_project

    if not project:
        return r.fail(
            code='NO_OPEN_PROJECT',
            message='No project is open. Unable to sync'
        ).response.flask_serialize()

    parts = relative_path.replace('\\', '/').strip('/').split('/')

    root_directory = project.source_directory
    file_path = os.path.join(root_directory, *parts)
    parent_directory = os.path.dirname(file_path)

    if not os.path.exists(parent_directory):
        os.makedirs(parent_directory)

    sync.io.write_file_chunk(file_path, chunk, append=index > 0)

    sync_status.update(time=sync_time)

    return r.notify(
        kind='SUCCESS',
        code='SAVED_CHUNK',
        message='Saved file chunk'
    ).response.flask_serialize()


@server_runner.APPLICATION.route(
    '/download/<filename>',
    methods=['GET', 'POST']
)
def download_file(filename: str):
    """ downloads the specified project file if it exists """

    project = cd.project.internal_project
    source_directory = project.source_directory if project else None

    if not filename or not project or not source_directory:
        return '', 204

    path = os.path.realpath(os.path.join(
        source_directory,
        '..',
        'downloads',
        filename
    ))

    if not os.path.exists(path):
        return '', 204

    return flask.send_file(path, mimetype=mimetypes.guess_type(path)[0])

