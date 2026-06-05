"""Unit tests for the antigravity launcher script.

All network I/O is mocked so the suite runs fully offline.

Run with:
    python -m pytest tests/ -v
    python -m unittest tests/test_antigravity.py -v
"""

import gzip
import importlib.machinery
import importlib.util
import os
import stat
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Load the antigravity script as a module (no .py extension)
# ---------------------------------------------------------------------------
_SCRIPT = os.path.join(os.path.dirname(__file__), "..", "antigravity")
_loader = importlib.machinery.SourceFileLoader("_ag", os.path.abspath(_SCRIPT))
_spec = importlib.util.spec_from_loader("_ag", _loader)
ag = importlib.util.module_from_spec(_spec)
_loader.exec_module(ag)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_executable(path: str) -> None:
    st = os.stat(path)
    os.chmod(path, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def _write(path: str, content: str = "") -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)


def _make_js_with_sections(*sections) -> str:
    """Build a minimal JS snippet with one or more product sections.

    Each *sections* entry is a tuple ``(section_id, linux_x64_url, linux_arm_url)``.
    The sections are concatenated so the window-bounding logic can be tested.
    """
    parts = []
    for section_id, x64_url, arm_url in sections:
        arm_entry = f',{{buttonText:"Linux ARM64",href:"{arm_url}"}}' if arm_url else ""
        parts.append(
            f'{{id:"{section_id}",platforms:['
            f'{{os:"linux",links:['
            f'{{buttonText:"Linux x64",href:"{x64_url}"}}'
            f"{arm_entry}"
            f"]}},"
            f'{{os:"mac",links:[]}},'
            f"]}}"
        )
    return "junk_before=1;" + ";next_obj=".join(parts) + ";junk_after=2;"


HUB_LINUX_URL = (
    "https://storage.googleapis.com/antigravity-public/"
    "antigravity-hub/2.0.11-111/linux-x64/Antigravity.tar.gz"
)
IDE_LINUX_URL = (
    "https://edgedl.me.gvt1.com/edgedl/release2/j0qc3/antigravity/"
    "stable/2.0.4-222/linux-x64/Antigravity%20IDE.tar.gz"
)

MOCK_HTML = '<html><head><script src="main-ABCD.js"></script></head></html>'
MOCK_JS_HUB_ONLY = _make_js_with_sections(("antigravity-2", HUB_LINUX_URL, ""))
MOCK_JS_IDE_ONLY = _make_js_with_sections(("antigravity-ide", IDE_LINUX_URL, ""))
MOCK_JS_BOTH = _make_js_with_sections(
    ("antigravity-2", HUB_LINUX_URL, ""),
    ("antigravity-ide", IDE_LINUX_URL, ""),
)


# ---------------------------------------------------------------------------
# Tests: find_file_recursive
# ---------------------------------------------------------------------------


class TestFindFileRecursive(unittest.TestCase):
    """Tests for the recursive file-finding helper."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with
        self.root = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def _file(self, rel_path: str, executable: bool = False) -> str:
        full = os.path.join(self.root, rel_path)
        _write(full, "binary")
        if executable:
            _make_executable(full)
        return full

    def test_finds_by_name(self):
        """Basic match by exact filename."""
        f = self._file("a/antigravity", executable=True)
        self.assertEqual(ag.find_file_recursive(self.root, "antigravity"), f)

    def test_returns_none_when_missing(self):
        """Returns None when the file does not exist."""
        self.assertIsNone(ag.find_file_recursive(self.root, "antigravity"))

    def test_executable_filter_excludes_non_executable(self):
        """Non-executable files are excluded when is_executable=True."""
        self._file("a/antigravity", executable=False)
        self.assertIsNone(
            ag.find_file_recursive(self.root, "antigravity", is_executable=True)
        )

    def test_executable_filter_finds_executable(self):
        """Executable files are returned when is_executable=True."""
        f = self._file("a/antigravity", executable=True)
        self.assertEqual(
            ag.find_file_recursive(self.root, "antigravity", is_executable=True), f
        )

    def test_returns_shallowest_match(self):
        """When multiple matches exist, the shallowest path wins."""
        self._file("a/b/c/antigravity", executable=True)
        shallow = self._file("x/antigravity", executable=True)
        self.assertEqual(
            ag.find_file_recursive(self.root, "antigravity", is_executable=True),
            shallow,
        )

    def test_exact_name_match_only(self):
        """'antigravity-ide' must not match a search for 'antigravity'."""
        self._file("a/antigravity-ide", executable=True)
        self.assertIsNone(
            ag.find_file_recursive(self.root, "antigravity", is_executable=True)
        )


# ---------------------------------------------------------------------------
# Tests: find_icon_recursive
# ---------------------------------------------------------------------------


class TestFindIconRecursive(unittest.TestCase):
    """Tests for the icon-scoring heuristic."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with
        self.root = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def _icon(self, rel_path: str) -> str:
        full = os.path.join(self.root, rel_path)
        _write(full)
        return full

    def test_returns_none_when_no_images(self):
        """Returns None when only non-image files are present."""
        _write(os.path.join(self.root, "README.txt"))
        self.assertIsNone(ag.find_icon_recursive(self.root, "antigravity"))

    def test_code_beats_logo_beats_icon(self):
        """Scoring: code (+10) > logo (+8) > icon (+6)."""
        self._icon("res/icon.png")
        self._icon("res/logo.png")
        code = self._icon("res/code.png")
        self.assertEqual(ag.find_icon_recursive(self.root, "antigravity-ide"), code)

    def test_logo_beats_icon(self):
        """Scoring: logo (+8) > icon (+6)."""
        self._icon("res/icon.png")
        logo = self._icon("res/logo.png")
        self.assertEqual(ag.find_icon_recursive(self.root, "antigravity"), logo)

    def test_app_name_in_filename_adds_score(self):
        """A filename containing app_name gets +5; 'icon' still wins at +6."""
        icon = self._icon("res/icon.png")  # score 6
        self._icon("res/antigravity.png")  # score 5
        self.assertEqual(ag.find_icon_recursive(self.root, "antigravity"), icon)

    def test_svg_accepted(self):
        """SVG files are accepted alongside PNG."""
        svg = self._icon("res/code-icon.svg")
        self.assertEqual(ag.find_icon_recursive(self.root, "antigravity-ide"), svg)

    def test_non_image_extensions_ignored(self):
        """Non PNG/SVG files are ignored even if their name scores highly."""
        _write(os.path.join(self.root, "code.txt"))
        self.assertIsNone(ag.find_icon_recursive(self.root, "antigravity"))


# ---------------------------------------------------------------------------
# Tests: get_user_home / get_user_uid_gid
# ---------------------------------------------------------------------------


class TestUserResolution(unittest.TestCase):
    """Tests for sudo-aware user resolution helpers."""

    def test_get_user_home_no_sudo(self):
        """Without SUDO_USER, returns expanduser('~')."""
        env = {k: v for k, v in os.environ.items() if k != "SUDO_USER"}
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(ag.get_user_home(), os.path.expanduser("~"))

    def test_get_user_home_with_sudo_user(self):
        """With SUDO_USER set, returns that user's home directory."""
        fake_entry = MagicMock()
        fake_entry.pw_dir = "/home/fakeuser"
        with patch.dict(os.environ, {"SUDO_USER": "fakeuser"}):
            with patch("pwd.getpwnam", return_value=fake_entry):
                self.assertEqual(ag.get_user_home(), "/home/fakeuser")

    def test_get_user_uid_gid_no_sudo(self):
        """Without SUDO_UID/GID, returns the current process uid/gid."""
        env = {k: v for k, v in os.environ.items() if k not in ("SUDO_UID", "SUDO_GID")}
        with patch.dict(os.environ, env, clear=True):
            uid, gid = ag.get_user_uid_gid()
            self.assertEqual(uid, os.getuid())
            self.assertEqual(gid, os.getgid())

    def test_get_user_uid_gid_with_sudo(self):
        """With SUDO_UID/GID set, returns those values."""
        with patch.dict(os.environ, {"SUDO_UID": "1234", "SUDO_GID": "5678"}):
            uid, gid = ag.get_user_uid_gid()
            self.assertEqual(uid, 1234)
            self.assertEqual(gid, 5678)


# ---------------------------------------------------------------------------
# Tests: fetch_url
# ---------------------------------------------------------------------------


class TestFetchUrl(unittest.TestCase):
    """Tests for the HTTP fetch helper."""

    def _mock_response(self, body: bytes, encoding: str = "") -> MagicMock:
        info = MagicMock()
        info.get = lambda k, d=None: encoding if k == "Content-Encoding" else d
        resp = MagicMock()
        resp.read.return_value = body
        resp.info.return_value = info
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        return resp

    def test_plain_response(self):
        """Plain (non-gzip) responses are returned as-is."""
        resp = self._mock_response(b"hello")
        with patch("urllib.request.urlopen", return_value=resp):
            data, _ = ag.fetch_url("https://example.com")
        self.assertEqual(data, b"hello")

    def test_gzip_response_decompressed(self):
        """Gzip-encoded responses are transparently decompressed."""
        compressed = gzip.compress(b"hello gzip")
        resp = self._mock_response(compressed, encoding="gzip")
        with patch("urllib.request.urlopen", return_value=resp):
            data, _ = ag.fetch_url("https://example.com")
        self.assertEqual(data, b"hello gzip")

    def test_empty_body_with_gzip_header_does_not_crash(self):
        """HEAD responses may advertise gzip but carry an empty body."""
        resp = self._mock_response(b"", encoding="gzip")
        with patch("urllib.request.urlopen", return_value=resp):
            data, _ = ag.fetch_url("https://example.com", method="HEAD")
        self.assertEqual(data, b"")


# ---------------------------------------------------------------------------
# Tests: discover_download_url
# ---------------------------------------------------------------------------


class TestDiscoverDownloadUrl(unittest.TestCase):
    """Tests for the download-URL scraping logic (all network calls mocked)."""

    def _patch_fetch(
        self, html: str, js: str, last_modified: str = "Wed, 01 Jan 2025 00:00:00 GMT"
    ):
        """Patch fetch_url to serve *html* for page requests and *js* for bundle requests."""
        html_bytes = html.encode()
        js_bytes = js.encode()
        head_info = MagicMock()
        head_info.get = lambda k, d=None: last_modified if k == "Last-Modified" else d

        def fake_fetch(
            url, method="GET", headers=None, timeout=10
        ):  # pylint: disable=unused-argument
            if method == "HEAD":
                return b"", head_info
            if "main-" in url and url.endswith(".js"):
                return js_bytes, MagicMock()
            return html_bytes, MagicMock()

        return patch.object(ag, "fetch_url", side_effect=fake_fetch)

    def test_hub_returns_linux_url(self):
        """Hub scraping finds the linux-x64 URL in the antigravity-2 section."""
        with self._patch_fetch(MOCK_HTML, MOCK_JS_HUB_ONLY):
            url, lm = ag.discover_download_url("antigravity")
        self.assertIn("linux-x64", url)
        self.assertIn("antigravity-hub", url)
        self.assertTrue(lm)

    def test_ide_returns_linux_url(self):
        """IDE scraping finds the linux-x64 URL in the antigravity-ide section."""
        with self._patch_fetch(MOCK_HTML, MOCK_JS_IDE_ONLY):
            url, lm = ag.discover_download_url("antigravity-ide")
        self.assertIn("linux-x64", url)
        self.assertTrue(lm)

    def test_both_sections_hub_correct(self):
        """When both sections are present the hub URL is still correctly extracted."""
        with self._patch_fetch(MOCK_HTML, MOCK_JS_BOTH):
            url, _ = ag.discover_download_url("antigravity")
        self.assertIn("antigravity-hub", url)
        self.assertNotIn("antigravity-ide", url)

    def test_both_sections_ide_correct(self):
        """When both sections are present the IDE URL is still correctly extracted."""
        with self._patch_fetch(MOCK_HTML, MOCK_JS_BOTH):
            url, _ = ag.discover_download_url("antigravity-ide")
        # IDE downloads come from edgedl.me.gvt1.com, hub from storage.googleapis.com
        self.assertIn("edgedl.me.gvt1.com", url)

    def test_raises_if_no_js_bundle_found(self):
        """Raises RuntimeError when no main-*.js link is found in the page."""
        with self._patch_fetch("<html></html>", ""):
            with self.assertRaises(RuntimeError):
                ag.discover_download_url("antigravity")

    def test_raises_if_section_missing_from_js(self):
        """Raises RuntimeError when the product section is absent from the bundle."""
        js_wrong = _make_js_with_sections(("other-product", HUB_LINUX_URL, ""))
        with self._patch_fetch(MOCK_HTML, js_wrong):
            with self.assertRaises(RuntimeError):
                ag.discover_download_url("antigravity")

    def test_raises_if_no_linux_href_in_section(self):
        """Raises RuntimeError when no linux href exists in the product section."""
        js_no_linux = (
            'id:"antigravity-2",'
            'platforms:[{os:"mac",links:[{href:"https://example.com/Antigravity.dmg"}]}]'
        )
        with self._patch_fetch(MOCK_HTML, js_no_linux):
            with self.assertRaises(RuntimeError):
                ag.discover_download_url("antigravity")

    def test_uses_linux_arm_on_arm_arch(self):
        """On ARM hosts, the linux-arm URL is returned."""
        arm_url = HUB_LINUX_URL.replace("linux-x64", "linux-arm")
        js = _make_js_with_sections(("antigravity-2", HUB_LINUX_URL, arm_url))
        with self._patch_fetch(MOCK_HTML, js):
            with patch.object(ag.platform, "machine", return_value="aarch64"):
                url, _ = ag.discover_download_url("antigravity")
        self.assertIn("linux-arm", url)

    def test_download_page_fetch_failure_raises(self):
        """Network failure on the page fetch is wrapped in a RuntimeError."""
        with patch.object(ag, "fetch_url", side_effect=OSError("network error")):
            with self.assertRaises(RuntimeError):
                ag.discover_download_url("antigravity")


# ---------------------------------------------------------------------------
# Tests: write_desktop_entry
# ---------------------------------------------------------------------------


class TestWriteDesktopEntry(unittest.TestCase):
    """Tests for .desktop file generation."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with
        self.home = self._tmp.name
        self.app_dir = os.path.join(self.home, ".local", "opt", "antigravity")
        bin_path = os.path.join(self.app_dir, "antigravity")
        _write(bin_path, "binary")
        _make_executable(bin_path)
        _write(os.path.join(self.app_dir, "logo.png"))

    def tearDown(self):
        self._tmp.cleanup()

    def _write_entry(self, app_name: str = "antigravity") -> None:
        with patch.object(ag, "get_user_home", return_value=self.home):
            ag.write_desktop_entry(app_name, self.app_dir)

    def _read_desktop(self, app_name: str = "antigravity") -> str:
        path = os.path.join(
            self.home, ".local", "share", "applications", f"{app_name}.desktop"
        )
        with open(path, encoding="utf-8") as fh:
            return fh.read()

    def test_creates_desktop_file(self):
        """A .desktop file is created for the application."""
        self._write_entry()
        desktop = os.path.join(
            self.home, ".local", "share", "applications", "antigravity.desktop"
        )
        self.assertTrue(os.path.exists(desktop))

    def test_exec_points_to_wrapper_not_raw_binary(self):
        """Exec= must reference ~/.local/bin/<app>, not the raw installed binary."""
        self._write_entry()
        content = self._read_desktop()
        wrapper = os.path.join(self.home, ".local", "bin", "antigravity")
        self.assertIn(f"Exec={wrapper}", content)
        exec_value = content.split("Exec=")[1].split("\n")[0]
        self.assertNotIn(str(self.app_dir), exec_value)

    def test_icon_path_is_absolute(self):
        """The Icon= field must be an absolute path when an icon is found."""
        self._write_entry()
        content = self._read_desktop()
        icon_line = next(ln for ln in content.splitlines() if ln.startswith("Icon="))
        self.assertTrue(
            icon_line.startswith("Icon=/"), f"Expected absolute path: {icon_line}"
        )

    def test_desktop_file_has_no_leading_blank_line(self):
        """The file must begin with [Desktop Entry] with no preceding blank line."""
        self._write_entry()
        content = self._read_desktop()
        self.assertTrue(
            content.startswith("[Desktop Entry]"),
            "File must not have a leading blank line",
        )

    def test_ide_display_name(self):
        """Antigravity IDE gets the correct display name."""
        ide_dir = os.path.join(self.home, ".local", "opt", "antigravity-ide")
        bin_path = os.path.join(ide_dir, "antigravity-ide")
        _write(bin_path, "binary")
        _make_executable(bin_path)
        with patch.object(ag, "get_user_home", return_value=self.home):
            ag.write_desktop_entry("antigravity-ide", ide_dir)
        content = self._read_desktop("antigravity-ide")
        self.assertIn("Name=Antigravity IDE", content)

    def test_skips_gracefully_when_no_binary(self):
        """No .desktop file is created when the binary is missing."""
        with tempfile.TemporaryDirectory() as empty_dir:
            with patch.object(ag, "get_user_home", return_value=self.home):
                ag.write_desktop_entry("antigravity", empty_dir)
        desktop = os.path.join(
            self.home, ".local", "share", "applications", "antigravity.desktop"
        )
        self.assertFalse(os.path.exists(desktop))

    def test_fallback_icon_when_none_found(self):
        """Falls back to 'utilities-terminal' when no icon file exists."""
        os.remove(os.path.join(self.app_dir, "logo.png"))
        self._write_entry()
        content = self._read_desktop()
        icon_line = next(ln for ln in content.splitlines() if ln.startswith("Icon="))
        self.assertIn("utilities-terminal", icon_line)


# ---------------------------------------------------------------------------
# Tests: self_install
# ---------------------------------------------------------------------------


class TestSelfInstall(unittest.TestCase):
    """Tests for the self-installation logic."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with
        self.home = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_copies_script_and_creates_symlink(self):
        """Running from a non-installed path copies the script and creates a symlink."""
        src = os.path.join(self.home, "source_script")
        _write(src, "#!/usr/bin/env python3\n# script")
        _make_executable(src)

        with patch.object(sys, "argv", [src]):
            with patch.object(ag, "get_user_home", return_value=self.home):
                ag.self_install()

        target = os.path.join(self.home, ".local", "bin", "antigravity")
        symlink = os.path.join(self.home, ".local", "bin", "antigravity-ide")
        self.assertTrue(os.path.isfile(target))
        self.assertTrue(os.access(target, os.X_OK))
        self.assertTrue(os.path.islink(symlink))
        self.assertEqual(os.readlink(symlink), "antigravity")

    def test_skips_copy_when_already_installed(self):
        """No copy occurs when running from the target path itself."""
        target = os.path.join(self.home, ".local", "bin", "antigravity")
        os.makedirs(os.path.dirname(target), exist_ok=True)
        _write(target, "# installed")
        _make_executable(target)

        with patch.object(sys, "argv", [target]):
            with patch.object(ag, "get_user_home", return_value=self.home):
                with patch("shutil.copy2") as mock_copy:
                    ag.self_install()

        mock_copy.assert_not_called()


if __name__ == "__main__":
    unittest.main()
