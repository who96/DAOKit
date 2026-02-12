from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from skills.loader import SkillLoader, SkillLoaderError


def _write_skill(
    *,
    root: Path,
    name: str,
    version: str,
    hooks: list[dict[str, object]] | None = None,
) -> Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": "1.0.0",
        "name": name,
        "version": version,
        "description": f"{name} description",
        "hooks": hooks or [],
        "scripts": {},
    }
    (skill_dir / "skill.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    return skill_dir


class SkillLoaderTests(unittest.TestCase):
    def test_skills_can_be_discovered_and_loaded(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            _write_skill(root=root, name="alpha", version="1.0.0")
            _write_skill(root=root, name="beta", version="2.1.3")

            loader = SkillLoader(search_paths=[root])
            discovered = loader.discover()

            self.assertEqual([entry.manifest.name for entry in discovered], ["alpha", "beta"])
            loaded = loader.load_all()
            self.assertEqual(tuple(sorted(loaded.keys())), ("alpha", "beta"))
            self.assertEqual(loaded["beta"].manifest.version, "2.1.3")
            self.assertEqual(loaded["alpha"].path, (root / "alpha").resolve())

    def test_duplicate_skill_names_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root_a = Path(tempdir) / "skills-a"
            root_b = Path(tempdir) / "skills-b"
            root_a.mkdir(parents=True, exist_ok=True)
            root_b.mkdir(parents=True, exist_ok=True)
            _write_skill(root=root_a, name="shared", version="1.0.0")
            _write_skill(root=root_b, name="shared", version="2.0.0")

            loader = SkillLoader(search_paths=[root_a, root_b])
            with self.assertRaises(SkillLoaderError):
                loader.discover()

    def test_invalid_manifest_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            broken = root / "broken"
            broken.mkdir(parents=True, exist_ok=True)
            (broken / "skill.json").write_text(
                json.dumps(
                    {
                        "schema_version": "1.0.0",
                        "version": "1.0.0",
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            loader = SkillLoader(search_paths=[root])
            with self.assertRaises(SkillLoaderError):
                loader.discover()


if __name__ == "__main__":
    unittest.main()
