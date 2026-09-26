"""Exercise the actual native-run footer with a purely in-memory filesystem."""
import ast
import io
import json
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
import unittest


RUNNER = Path(__file__).with_name('targetmap_native_gbuffer.py')


class FakePath:
    def __init__(self, path, state):
        self.path = PurePosixPath(str(path))
        self.state = state

    def resolve(self):
        return self

    @property
    def parent(self):
        return FakePath(self.path.parent, self.state)

    def __truediv__(self, value):
        return FakePath(self.path / value, self.state)

    def __eq__(self, other):
        return isinstance(other, FakePath) and self.path == other.path

    def exists(self):
        return str(self.path) in self.state['directories']

    def mkdir(self, exist_ok=False):
        self.state['mkdir_attempts'].append(str(self.path))
        if self.exists() and not exist_ok:
            raise FileExistsError(str(self.path))
        self.state['directories'].add(str(self.path))

    def open(self, mode, encoding=None):
        self.state['write_attempts'].append((str(self.path), mode))
        return io.StringIO()


class OutputOwnershipTests(unittest.TestCase):
    def run_footer(self, requested, existing=(), fail_run=False):
        tree = ast.parse(RUNNER.read_text(encoding='utf-8'))
        # Execute only the real footer, not imports or run() and never Falcor.
        first = next(i for i, node in enumerate(tree.body)
                     if isinstance(node, ast.Assign)
                     and any(isinstance(target, ast.Name) and target.id == 'out' for target in node.targets))
        footer = compile(ast.Module(body=tree.body[first:], type_ignores=[]), str(RUNNER), 'exec')
        state = dict(directories=set(existing), mkdir_attempts=[], write_attempts=[], run_calls=0)

        def run(output):
            state['run_calls'] += 1
            if fail_run:
                raise RuntimeError('simulated rendering failure after directory ownership')
            return {'status': 'rendered_not_parity'}

        namespace = {'ROOT': FakePath('/workspace', state),
                     'Path': lambda path: FakePath(path, state),
                     'os': SimpleNamespace(environ={} if requested is None else {'CRP_TARGETMAP_NATIVE_OUT': requested}),
                     'json': json, 'run': run, 'print': lambda *args, **kwargs: None,
                     'traceback': SimpleNamespace(format_exc=lambda: 'expected test failure', print_exc=lambda: None),
                     'exit': lambda: None}
        exec(footer, namespace)
        return state

    def test_rejected_outside_existing_directory_is_never_written(self):
        state = self.run_footer('/unrelated/existing', existing=['/unrelated/existing'])
        self.assertEqual(state['run_calls'], 0)
        self.assertEqual(state['mkdir_attempts'], [])
        self.assertEqual(state['write_attempts'], [])

    def test_existing_in_scope_directory_is_never_written(self):
        output = '/workspace/build/targetmap-shading-a1/previous-run'
        state = self.run_footer(output, existing=[output])
        self.assertEqual(state['run_calls'], 0)
        self.assertEqual(state['write_attempts'], [])

    def test_new_owned_success_has_one_exclusive_result(self):
        output = '/workspace/build/targetmap-shading-a1/new-run'
        state = self.run_footer(output)
        self.assertEqual(state['run_calls'], 1)
        self.assertEqual(state['write_attempts'], [(output + '/result.json', 'x')])

    def test_new_owned_failure_still_records_one_exclusive_result(self):
        output = '/workspace/build/targetmap-shading-a1/new-failed-run'
        state = self.run_footer(output, fail_run=True)
        self.assertEqual(state['run_calls'], 1)
        self.assertEqual(state['write_attempts'], [(output + '/result.json', 'x')])

    def test_missing_output_environment_is_never_written(self):
        state = self.run_footer(None)
        self.assertEqual(state['run_calls'], 0)
        self.assertEqual(state['write_attempts'], [])


if __name__ == '__main__':
    unittest.main()
