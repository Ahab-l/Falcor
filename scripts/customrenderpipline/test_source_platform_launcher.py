"""Source module packaging contract; no engine execution."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from source_assets import launch_platform_texture as launcher


class LoaderManifestTests(unittest.TestCase):
    def test_source_ddc_seed_copies_only_into_new_owned_cache(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(launcher, 'BASE', Path(temp)):
            root = Path(temp); old=root/'old'; new=root/'new'
            (old/'DDC/Content').mkdir(parents=True)
            (old/'DDC/Content/test').write_bytes(b'source-built-cache')
            (new/'DDC').mkdir(parents=True)
            launcher.seed_source_ddc(new, old)
            self.assertEqual((new/'DDC/Content/test').read_bytes(), b'source-built-cache')
            self.assertEqual((old/'DDC/Content/test').read_bytes(), b'source-built-cache')
            with self.assertRaises(ValueError):
                launcher.seed_source_ddc(new, old)
            with self.assertRaises(ValueError):
                launcher.seed_source_ddc(new, root.parent/'outside')

    def test_post_main_drains_compilation_before_python_shutdown_gc(self):
        source = (Path(launcher.__file__).parent/'SourceTextureExport/Source/SourceTextureExport/Private/SourceTextureExport.cpp').read_text()
        self.assertIn('FCoreDelegates::OnCommandletPostMain.AddLambda', source)
        self.assertIn('FAssetCompilingManager::Get().FinishAllCompilation()', source)
        self.assertIn('GShaderCompilingManager->FinishAllCompilation()', source)
        self.assertIn('SOURCE_TEXTURE_COMPILE_DRAIN', source)
        self.assertIn('OnCommandletPostMain.Remove', source)

    def test_export_enables_source_platform_data_without_visible_window(self):
        run = Path('scratch-run')
        command = launcher.export_command(run, {'project': str(run/'Scratch/SourceTextureScratch.uproject')})
        self.assertIn('-AllowCommandletRendering', command)
        self.assertIn('-RenderOffscreen', command)
        self.assertIn('-d3d12', command)
        self.assertNotIn('-NullRHI', command)
        self.assertNotIn('-NoShaderCompile', command)
        self.assertIn('-corelimit=4', command)
        self.assertIn('-NoRemoteShaderCompile', command)
        self.assertIn('-DDC=SourceTextureExport', command)

    def fixture(self, root):
        run = root/'run'
        binary = run/'Scratch/Plugins/SourceTextureExport/Binaries/Win64'
        binary.mkdir(parents=True)
        dll = binary/'UnrealEditor-SourceTextureExport-Win64-Debug.dll'
        dll.write_bytes(b'compiled-owned-fixture')
        engine = root/'engine.modules'
        engine.write_text(json.dumps({'BuildId': 'source-engine-build', 'Modules': {'Engine': 'UnrealEditor-Engine-Win64-Debug.dll'}}))
        (run/'build-1.result.json').write_text(json.dumps({'exit_code': 0}))
        return run, engine, dll

    def test_publishes_only_owned_module_and_is_repeatable(self):
        with tempfile.TemporaryDirectory() as temp:
            run, engine, dll = self.fixture(Path(temp))
            original = engine.read_bytes()
            record = launcher.prepare_loader(run, engine)
            manifest = json.loads(Path(record['manifest']['path']).read_text())
            self.assertEqual(manifest, {'BuildId': 'source-engine-build', 'Modules': {'SourceTextureExport': dll.name}})
            self.assertEqual(engine.read_bytes(), original)
            self.assertEqual(launcher.prepare_loader(run, engine), record)

    def test_rejects_changed_compiled_module(self):
        with tempfile.TemporaryDirectory() as temp:
            run, engine, dll = self.fixture(Path(temp))
            launcher.prepare_loader(run, engine)
            dll.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'changed'):
                launcher.prepare_loader(run, engine)

    def test_requires_successful_build_and_never_overwrites_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            run, engine, dll = self.fixture(Path(temp))
            (run/'build-1.result.json').write_text('{"exit_code": 1}')
            with self.assertRaisesRegex(ValueError, 'successful'):
                launcher.prepare_loader(run, engine)
            (run/'build-1.result.json').write_text('{"exit_code": 0}')
            target = dll.parent/'UnrealEditor-Win64-Debug.modules'
            target.write_bytes(b'existing')
            with self.assertRaises(FileExistsError):
                launcher.prepare_loader(run, engine)
            self.assertEqual(target.read_bytes(), b'existing')


if __name__ == '__main__':
    unittest.main()
