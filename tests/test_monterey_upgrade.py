"""Regression tests for the Monterey hardening fork."""
from __future__ import annotations
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock,patch
from apple_photos_to_immich import commands
from apple_photos_to_immich.config import Config
from apple_photos_to_immich.audit import audit_export
from apple_photos_to_immich.metadata_check import iso_day
from apple_photos_to_immich.gui import ACTIONS,make_config,read_config,save_private_config
from apple_photos_to_immich.config import load_config
from apple_photos_to_immich.matching import match_assets

class HardeningTests(unittest.TestCase):
    def config(self,folder):
        p=Path(folder)
        return Config(immich_server="http://localhost:2283",immich_api_key="secret-sample",
                      photos_library=str(p/"Library.photoslibrary"),
                      export_dir=p/"export",meta_dir=p/"meta")
    def test_sample_never_uploads(self):
        with tempfile.TemporaryDirectory() as root:
            c=self.config(root)
            with patch.object(commands,"check",return_value=0),patch.object(commands,"export_assets",return_value=0) as exp,patch.object(commands,"import_assets") as upload,patch.object(commands,"apply_albums") as albums:
                self.assertEqual(commands.run_all(c,MagicMock(),test_mode=True),0)
            exp.assert_called_once()
            self.assertTrue(exp.call_args.kwargs["test_mode"])
            upload.assert_not_called();albums.assert_not_called()
            self.assertFalse(c.state_path.exists())
    def test_verification_failure_propagates(self):
        with tempfile.TemporaryDirectory() as root:
            c=self.config(root)
            mocks={"check":0,"export_assets":0,"import_assets":0,"wait_for_immich":0,
                   "make_album_map":0,"apply_albums":0,"verify":2}
            from contextlib import ExitStack
            with ExitStack() as stack:
                for name,value in mocks.items():stack.enter_context(patch.object(commands,name,return_value=value))
                rc=commands.run_all(c,MagicMock())
            self.assertEqual(rc,2)
            state=json.loads(c.state_path.read_text())
            self.assertNotIn("verify",state["completedSteps"])
    def test_resume_detects_different_server(self):
        with tempfile.TemporaryDirectory() as root:
            c=self.config(root)
            from contextlib import ExitStack
            with ExitStack() as stack:
                for name in ("check","export_assets","import_assets","wait_for_immich",
                             "make_album_map","apply_albums","verify"):
                    stack.enter_context(patch.object(commands,name,return_value=0))
                self.assertEqual(commands.run_all(c,MagicMock()),0)
            c.immich_server="https://another-host.invalid"
            self.assertEqual(commands.run_all(c,MagicMock()),1)
    def test_strict_matching(self):
        u="AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA"
        apple={u:{"originalFilename":"IMG_0001.JPG","date":"2025-01-02"}}
        target=[{"id":"other","originalFileName":"IMG_0001.JPG","fileCreatedAt":"2025-01-02T03:00:00Z"}]
        result=match_assets(apple,target,allow_filename_date_fallback=False)
        self.assertEqual(result.missing_uuids,[u])
    def test_secret_outside_argv(self):
        with tempfile.TemporaryDirectory() as root:
            c=self.config(root)
            with patch.object(commands.subprocess,"run",return_value=MagicMock(returncode=0)) as run:
                self.assertEqual(commands.import_assets(c,MagicMock()),0)
            argv=run.call_args.args[0]
            self.assertNotIn(c.immich_api_key," ".join(argv))
            self.assertEqual(run.call_args.kwargs["env"]["IMMICH_GO_UPLOAD_API_KEY"],c.immich_api_key)
            self.assertIn("--no-ui",argv)
    def test_audit_counts_without_modifying(self):
        with tempfile.TemporaryDirectory() as root:
            c=self.config(root)
            c.export_dir.mkdir()
            (c.export_dir/"a.jpg").write_bytes(b"photo")
            (c.export_dir/"a.xmp").write_text("xmp")
            self.assertEqual(audit_export(c,MagicMock(),sha256=True),0)
            result=json.loads((c.meta_dir/"audit-export.json").read_text())
            self.assertEqual(result["mediaFiles"],1)
            self.assertEqual(result["sha256Files"][0]["path"],"a.jpg")
    def test_private_config(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/"config.toml"
            values={"server":"https://immich.local","api_key":'a"secret',
                    "library":"/tmp/Library.photoslibrary","export_dir":"/tmp/export","meta_dir":"/tmp/meta"}
            save_private_config(path,make_config(values))
            self.assertEqual(path.stat().st_mode&0o777,0o600)
            self.assertEqual(read_config(path)["api_key"],values["api_key"])
    def test_gui_covers_core_steps(self):
        actions={a[2] for a in ACTIONS}
        for op in ("check","export --test","import-assets","make-map","apply-albums","verify","all"):
            self.assertIn(op,actions)
    def test_offline_configuration_and_local_check(self):
        with tempfile.TemporaryDirectory() as root:
            c=self.config(root)
            Path(c.photos_library).mkdir()
            c.immich_api_key=""
            values={"server":c.immich_server,"api_key":"","library":c.photos_library,
                    "export_dir":str(c.export_dir),"meta_dir":str(c.meta_dir)}
            path=Path(root)/"config.toml"
            save_private_config(path,make_config(values))
            loaded=load_config(path)
            self.assertEqual(loaded.immich_api_key,"")
            with patch.object(commands.shutil,"which",side_effect=lambda name: "/fake/osxphotos" if name=="osxphotos" else None):
                self.assertEqual(commands.check(loaded,MagicMock(),require_immich=False),0)
                self.assertEqual(commands.check(loaded,MagicMock(),require_immich=True),1)
    def test_date_parser(self):
        self.assertEqual(iso_day("2020-01-03T09:10:00Z"),"2020-01-03")

if __name__=="__main__":unittest.main()
