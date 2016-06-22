import re
import typing
from argparse import ArgumentParser

import cauldron
from cauldron import cli
from cauldron import environ
from cauldron import runner
from cauldron.cli import autocompletion
from cauldron.cli.commands.run import actions as run_actions

DESCRIPTION = cli.reformat("""
    Runs one or more steps within the currently opened project
    """)


def populate(parser: ArgumentParser):
    """

    :param parser:
    :return:
    """

    parser.add_argument(
        'step',
        nargs='*',
        default=None,
        help=cli.reformat("""
            The name of the step, or a space-separated list of steps to be run.
            If this argument is omitted, all steps in the project will be run.
            """)
    )

    parser.add_argument(
        '-f', '--force',
        dest='force',
        default=False,
        action='store_true',
        help=cli.reformat("""
            When this option is included, the step or steps will run even if
            they have not been modified. This is useful when you've updated
            external data or code, but not the project code file(s).
            """)
    )

    parser.add_argument(
        '-c', '--continue',
        dest='continue_after',
        default=False,
        action='store_true',
        help=cli.reformat("""
            When this option is included, all steps after the one specified
            will be run as well as the specified step.
            """)
    )

    parser.add_argument(
        '-s', '--step',
        dest='single_step',
        default=False,
        action='store_true',
        help=cli.reformat("""
            When this option is included, only the first step that needs to be
            updated will be run.
            """)
    )

    parser.add_argument(
        '-l', '--limit',
        dest='limit',
        default=-1,
        type=int,
        help=cli.reformat("""
            The maximum number of steps to run including any specified first
            step. Useful is you want to run only a section of the project.
            """)
    )


def execute(
        parser: ArgumentParser,
        step: list,
        force: bool = False,
        continue_after: bool = False,
        single_step: bool = False,
        limit: int = -1
):
    """

    :param parser:
    :param step:
    :param force:
    :param continue_after:
    :param single_step:
    :param limit:
    :return:
    """

    project = run_actions.get_project()
    if not project:
        return

    run_actions.preload_project(project)

    if not step:
        step = []
    else:
        step = [s.strip('"') for s in step]

    try:
        # Special cases that apply limits
        if re.match(r'[0-9]+$', step[-1]):
            limit = int(step[-1])
            step.pop()
        elif re.match(r'[\.]+', step[-1]):
            limit = len(step[-1])
            step.pop()
    except Exception:
        pass

    project_steps = []
    for s in project.steps:
        if s.definition.name in step:
            project_steps.append(s)

    for ps in project_steps:
        step.remove(ps.definition.name)

    if len(step) > 0:
        message = ['  * "{}"'.format(x) for x in step]
        message.insert(0, '[ABORTED]: Unable to locate the following step(s):')
        environ.output.fail().notify(
            kind='ABORTED',
            code='MISSING_STEP',
            message='Unable to locate steps'
        ).kernel(
            steps=[x for x in step]
        ).console(
            message,
            whitespace=1
        )
        return

    has_dirty_dependency = False
    for dep in project.dependencies:
        if dep.is_dirty():
            has_dirty_dependency = True
            break

    if has_dirty_dependency:
        environ.log_header('SOURCING', 5)
        if not runner.dependencies(project):
            return

    environ.log_header('RUNNING', 5)

    if single_step:
        # If the user specifies the single step flag, only run one step. Force
        # the step to be run if they specified it explicitly

        ps = project_steps[0] if len(project_steps) > 0 else None
        force = force or (single_step and bool(ps is not None))
        runner.section(project, ps, limit=1, force=force)

    elif continue_after or len(project_steps) == 0:
        # If the continue after flag is set, start with the specified step
        # and run the rest of the project after that. Or, if no steps were
        # specified, run the entire project with the specified flags.

        ps = project_steps[0] if len(project_steps) > 0 else None
        runner.complete(project, ps, force=force, limit=limit)
        environ.log_blanks()
        return

    else:
        has_run = []
        for ps in project_steps:
            if ps in has_run:
                continue

            has_run += runner.section(
                project, ps,
                limit=max(1, limit),
                force=force or (limit < 1 and len(project_steps) < 2)
            )

    project.write()
    environ.log_blanks()


def autocomplete(segment: str, line: str, parts: typing.List[str]):
    """

    :param segment:
    :param line:
    :param parts:
    :return:
    """

    if parts[-1].startswith('-'):
        return autocompletion.match_flags(
            segment=segment,
            value=parts[-1],
            shorts=['f', 'c', 's', 'l'],
            longs=['force', 'continue', 'step', 'limit']
        )

    if len(parts) < 1:
        return []

    value = parts[-1]
    project = cauldron.project.internal_project
    step_names = [x.definition.name for x in project.steps]
    return autocompletion.match_in_path_list(segment, value, step_names)


