# pylint: disable=too-many-lines
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
# Tests: is_sandbox_configured
# ---------------------------------------------------------------------------


class TestIsSandboxConfigured(unittest.TestCase):
    """Tests for sandbox usability helper."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with
        self.root = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_returns_true_when_no_sandbox_binary_and_userns_works(self):
        """Returns True when chrome-sandbox is missing and user namespaces work."""
        with (
            patch("os.path.exists", return_value=False),
            patch("os.fork", return_value=123),
            patch("os.waitpid", return_value=(123, 0)),
        ):
            self.assertTrue(ag.is_sandbox_usable(self.root))

    def test_returns_false_when_userns_clone_disabled_sysctl(self):
        """Returns False when /proc/sys/kernel/unprivileged_userns_clone is 0."""
        with (
            patch(
                "os.path.exists", side_effect=lambda p: "unprivileged_userns_clone" in p
            ),
            patch("builtins.open", unittest.mock.mock_open(read_data="0")),
        ):
            self.assertFalse(ag.is_sandbox_usable(self.root))

    def test_returns_false_when_max_userns_zero_sysctl(self):
        """Returns False when /proc/sys/user/max_user_namespaces is 0."""
        with (
            patch("os.path.exists", side_effect=lambda p: "max_user_namespaces" in p),
            patch("builtins.open", unittest.mock.mock_open(read_data="0")),
        ):
            self.assertFalse(ag.is_sandbox_usable(self.root))

    def test_returns_false_when_userns_unshare_fails(self):
        """Returns False when unshare(CLONE_NEWUSER) fails."""
        with (
            patch("os.path.exists", return_value=False),
            patch("os.fork", return_value=123),
            patch("os.waitpid", return_value=(123, 1 << 8)),
        ):
            self.assertFalse(ag.is_sandbox_usable(self.root))

    def test_returns_false_when_not_root_or_not_setuid(self):
        """Returns False when chrome-sandbox is owned by normal user or lacks setuid."""
        sb = os.path.join(self.root, "chrome-sandbox")
        _write(sb)
        self.assertFalse(ag.is_sandbox_usable(self.root))

    def test_returns_true_when_root_owned_and_setuid(self):
        """Returns True when chrome-sandbox is root-owned with SUID set."""
        sb = os.path.join(self.root, "chrome-sandbox")
        _write(sb)
        fake_stat = MagicMock()
        fake_stat.st_uid = 0
        fake_stat.st_mode = stat.S_ISUID | 0o755
        with patch("os.stat", return_value=fake_stat):
            self.assertTrue(ag.is_sandbox_usable(self.root))


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

    def test_html_direct_section_hub_and_ide(self):
        """Discovers URLs directly embedded in HTML without JS bundles."""
        mock_html_direct = (
            "<html><body>"
            f'<div id="antigravity-2"><a href="{HUB_LINUX_URL}">Download</a></div>'
            f'<div id="antigravity-ide"><a href="{IDE_LINUX_URL}">Download</a></div>'
            "</body></html>"
        )
        with self._patch_fetch(mock_html_direct, ""):
            hub_url, _ = ag.discover_download_url("antigravity")
            ide_url, _ = ag.discover_download_url("antigravity-ide")
        self.assertEqual(hub_url, HUB_LINUX_URL)
        self.assertEqual(ide_url, IDE_LINUX_URL)


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
        self._env_patch = patch.dict(os.environ, {"ANTIGRAVITY_INSTALL_MODE": "user"})
        self._env_patch.start()

    def tearDown(self):
        self._env_patch.stop()
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

    def test_privileged_non_root_writes_desktop_with_sudo(self):
        """When privileged mode is active and non-root, writes desktop entry via sudo."""
        with patch.object(ag, "is_privileged_mode", return_value=True):
            with patch.object(os, "getuid", return_value=1000):
                with patch.object(ag, "can_use_sudo", return_value=True):
                    with patch("subprocess.run") as mock_run:
                        mock_run.return_value = MagicMock(returncode=0)
                        ag.write_desktop_entry(
                            "antigravity", self.app_dir, privileged=True
                        )

        sudo_calls = [
            call_args[0][0]
            for call_args in mock_run.call_args_list
            if isinstance(call_args[0][0], list) and call_args[0][0][0] == "sudo"
        ]
        self.assertTrue(any("cp" in c for c in sudo_calls))


# ---------------------------------------------------------------------------
# Tests: self_install
# ---------------------------------------------------------------------------


class TestSelfInstall(unittest.TestCase):
    """Tests for the self-installation logic."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with
        self.home = self._tmp.name
        self._env_patch = patch.dict(os.environ, {"ANTIGRAVITY_INSTALL_MODE": "user"})
        self._env_patch.start()

    def tearDown(self):
        self._env_patch.stop()
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

    def test_privileged_non_root_uses_sudo(self):
        """When privileged mode is on and non-root, uses sudo to install and link."""
        src = os.path.join(self.home, "source_script")
        _write(src, "#!/usr/bin/env python3\n# script")
        _make_executable(src)

        with patch.object(sys, "argv", [src]):
            with patch.object(ag, "is_privileged_mode", return_value=True):
                with patch.object(os, "getuid", return_value=1000):
                    with patch.object(ag, "can_use_sudo", return_value=True):
                        with patch.object(os.path, "lexists", return_value=False):
                            with patch("subprocess.run") as mock_run:
                                mock_run.return_value = MagicMock(returncode=0)
                                ag.self_install(privileged=True)

        # Should invoke sudo for mkdir, cp, chmod, and ln
        self.assertTrue(mock_run.called)
        sudo_calls = [
            call_args[0][0]
            for call_args in mock_run.call_args_list
            if isinstance(call_args[0][0], list) and call_args[0][0][0] == "sudo"
        ]
        self.assertTrue(any("cp" in c for c in sudo_calls))
        self.assertTrue(any("ln" in c for c in sudo_calls))

    def test_privileged_already_installed_creates_symlink_with_sudo(self):
        """When running from /usr/local/bin, missing symlink is created via sudo."""
        target = "/usr/local/bin/antigravity"
        with patch.object(sys, "argv", [target]):
            with patch.object(ag, "is_privileged_mode", return_value=True):
                with patch.object(os, "getuid", return_value=1000):
                    with patch.object(ag, "can_use_sudo", return_value=True):
                        with patch.object(os.path, "lexists", return_value=False):
                            with patch("subprocess.run") as mock_run:
                                mock_run.return_value = MagicMock(returncode=0)
                                ag.self_install(privileged=True)

        sudo_calls = [
            call_args[0][0]
            for call_args in mock_run.call_args_list
            if isinstance(call_args[0][0], list) and call_args[0][0][0] == "sudo"
        ]
        self.assertTrue(any("ln" in c for c in sudo_calls))


# ---------------------------------------------------------------------------
# Tests: self_update
# ---------------------------------------------------------------------------


class TestSelfUpdate(unittest.TestCase):
    """Tests for the self-update logic."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with
        self.home = self._tmp.name
        self.script_path = os.path.join(self.home, "antigravity")
        _write(self.script_path, "#!/usr/bin/env python3\n# old version")
        _make_executable(self.script_path)

    def tearDown(self):
        self._tmp.cleanup()

    def test_skips_when_remote_matches_local(self):
        """When remote script matches local script, no write or re-exec happens."""
        with patch.object(sys, "argv", [self.script_path]):
            with patch.object(
                ag,
                "fetch_url",
                return_value=(b"#!/usr/bin/env python3\n# old version", MagicMock()),
            ):
                with patch("os.execv") as mock_execv:
                    ag.self_update()

        mock_execv.assert_not_called()
        with open(self.script_path, "r", encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "#!/usr/bin/env python3\n# old version")

    def test_updates_file_and_reexecs_when_different(self):
        """When remote script is different, updates file, sets +x, and re-execs."""
        new_content = b"#!/usr/bin/env python3\n# new version\n"
        with patch.object(sys, "argv", [self.script_path, "--arg1"]):
            with patch.object(ag, "fetch_url", return_value=(new_content, MagicMock())):
                with patch("os.execv") as mock_execv:
                    ag.self_update()

        with open(self.script_path, "rb") as fh:
            self.assertEqual(fh.read(), new_content)
        self.assertTrue(os.access(self.script_path, os.X_OK))

        mock_execv.assert_called_once_with(
            sys.executable, [sys.executable, self.script_path, "--arg1"]
        )

    def test_gracefully_handles_fetch_error(self):
        """When fetching the remote script fails, it logs a warning and returns."""
        with patch.object(sys, "argv", [self.script_path]):
            with patch.object(ag, "fetch_url", side_effect=OSError("Network error")):
                with patch("os.execv") as mock_execv:
                    ag.self_update()

        mock_execv.assert_not_called()
        with open(self.script_path, "r", encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "#!/usr/bin/env python3\n# old version")

    def test_gracefully_handles_write_error(self):
        """When writing updated script fails, no re-exec is triggered."""
        new_content = b"#!/usr/bin/env python3\n# new version\n"
        with patch.object(sys, "argv", [self.script_path]):
            with patch.object(ag, "fetch_url", return_value=(new_content, MagicMock())):
                with patch("os.replace", side_effect=OSError("Permission denied")):
                    with patch("os.execv") as mock_execv:
                        ag.self_update()

        mock_execv.assert_not_called()

    def test_updates_target_of_symlink(self):
        """When running via a symlink, the target file is updated."""
        symlink_path = os.path.join(self.home, "antigravity-ide")
        os.symlink(self.script_path, symlink_path)
        new_content = b"#!/usr/bin/env python3\n# new version\n"

        with patch.object(sys, "argv", [symlink_path]):
            with patch.object(ag, "fetch_url", return_value=(new_content, MagicMock())):
                with patch("os.execv") as mock_execv:
                    ag.self_update()

        self.assertTrue(os.path.islink(symlink_path))
        with open(self.script_path, "rb") as fh:
            self.assertEqual(fh.read(), new_content)
        mock_execv.assert_called_once_with(
            sys.executable, [sys.executable, symlink_path]
        )

    def test_skips_when_script_file_missing(self):
        """When script path does not exist on disk, returns without error."""
        non_existent = os.path.join(self.home, "non_existent")
        with patch.object(sys, "argv", [non_existent]):
            with patch.object(ag, "fetch_url") as mock_fetch:
                ag.self_update()

        mock_fetch.assert_not_called()

    def test_updates_via_sudo_when_not_writable(self):
        """When script is not writable and sudo is available, updates via sudo."""
        new_content = b"#!/usr/bin/env python3\n# new sudo version\n"
        with patch.object(sys, "argv", [self.script_path]):
            with patch.object(ag, "fetch_url", return_value=(new_content, MagicMock())):
                with patch.object(os, "access", return_value=False):
                    with patch.object(ag, "can_use_sudo", return_value=True):
                        with patch("subprocess.run") as mock_run:
                            mock_run.return_value = MagicMock(returncode=0)
                            with patch("os.execv") as mock_execv:
                                ag.self_update()

        sudo_calls = [
            call_args[0][0]
            for call_args in mock_run.call_args_list
            if isinstance(call_args[0][0], list) and call_args[0][0][0] == "sudo"
        ]
        self.assertTrue(any("cp" in c for c in sudo_calls))
        mock_execv.assert_called_once()

    def test_main_invokes_self_update(self):
        """main() invokes self_update() before other operations."""
        with patch.object(ag, "self_update") as mock_self_update:
            with patch.object(ag, "self_install"):
                with patch.object(ag, "check_and_update"):
                    with patch.object(sys, "argv", ["antigravity", "--update"]):
                        with self.assertRaises(SystemExit):
                            ag.main()
        mock_self_update.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: detect_password_store
# ---------------------------------------------------------------------------


class TestDetectPasswordStore(unittest.TestCase):
    """Tests for the password-store detection logic."""

    def test_env_override(self):
        """ANTIGRAVITY_PASSWORD_STORE environment variable overrides detection."""
        with patch.dict(os.environ, {"ANTIGRAVITY_PASSWORD_STORE": "custom-store"}):
            self.assertEqual(ag.detect_password_store(), "custom-store")

    def test_kde_with_kwalletd6(self):
        """In KDE environment with kwalletd6 available, returns kwallet6."""
        with (
            patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "KDE"}, clear=True),
            patch(
                "shutil.which",
                side_effect=lambda cmd: (
                    "/usr/bin/kwalletd6" if cmd == "kwalletd6" else None
                ),
            ),
        ):
            self.assertEqual(ag.detect_password_store(), "kwallet6")

    def test_kde_with_kwalletd5(self):
        """In KDE environment with kwalletd5 available, returns kwallet5."""
        with (
            patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "KDE"}, clear=True),
            patch(
                "shutil.which",
                side_effect=lambda cmd: (
                    "/usr/bin/kwalletd5" if cmd == "kwalletd5" else None
                ),
            ),
        ):
            self.assertEqual(ag.detect_password_store(), "kwallet5")

    def test_kde_with_kwalletd(self):
        """In KDE environment with kwalletd available, returns kwallet."""
        with (
            patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "KDE"}, clear=True),
            patch(
                "shutil.which",
                side_effect=lambda cmd: (
                    "/usr/bin/kwalletd" if cmd == "kwalletd" else None
                ),
            ),
        ):
            self.assertEqual(ag.detect_password_store(), "kwallet")

    def test_kde_with_gnome_keyring(self):
        """In KDE environment with gnome-keyring-daemon, returns gnome-libsecret."""
        with (
            patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "KDE"}, clear=True),
            patch(
                "shutil.which",
                side_effect=lambda cmd: (
                    "/usr/bin/gnome-keyring-daemon"
                    if cmd == "gnome-keyring-daemon"
                    else None
                ),
            ),
        ):
            self.assertEqual(ag.detect_password_store(), "gnome-libsecret")

    def test_kde_fallback_defaults_to_kwallet5(self):
        """In KDE environment without detected binaries, returns kwallet5."""
        with (
            patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "KDE"}, clear=True),
            patch("shutil.which", return_value=None),
        ):
            self.assertEqual(ag.detect_password_store(), "kwallet5")

    def test_gnome_keyring_daemon_found(self):
        """When gnome-keyring-daemon is present, returns gnome-libsecret."""
        with (
            patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "XFCE"}, clear=True),
            patch(
                "shutil.which",
                side_effect=lambda cmd: (
                    "/usr/bin/gnome-keyring-daemon"
                    if cmd == "gnome-keyring-daemon"
                    else None
                ),
            ),
        ):
            self.assertEqual(ag.detect_password_store(), "gnome-libsecret")

    def test_secret_tool_found(self):
        """When secret-tool is present, returns gnome-libsecret."""
        with (
            patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "awesome"}, clear=True),
            patch(
                "shutil.which",
                side_effect=lambda cmd: (
                    "/usr/bin/secret-tool" if cmd == "secret-tool" else None
                ),
            ),
            patch("os.path.exists", return_value=False),
        ):
            self.assertEqual(ag.detect_password_store(), "gnome-libsecret")

    def test_keepassxc_found(self):
        """When keepassxc is present, returns gnome-libsecret."""
        with (
            patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "i3"}, clear=True),
            patch(
                "shutil.which",
                side_effect=lambda cmd: (
                    "/usr/bin/keepassxc" if cmd == "keepassxc" else None
                ),
            ),
            patch("os.path.exists", return_value=False),
        ):
            self.assertEqual(ag.detect_password_store(), "gnome-libsecret")

    def test_kwallet_found_on_other_desktop(self):
        """When kwalletd6 is present on a non-KDE desktop, returns kwallet6."""
        with (
            patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "i3"}, clear=True),
            patch(
                "shutil.which",
                side_effect=lambda cmd: (
                    "/usr/bin/kwalletd6" if cmd == "kwalletd6" else None
                ),
            ),
            patch("os.path.exists", return_value=False),
        ):
            self.assertEqual(ag.detect_password_store(), "kwallet6")

    def test_gnome_desktop_without_binaries_fallback(self):
        """On GNOME desktop without binaries detected, returns gnome-libsecret."""
        with (
            patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "ubuntu:GNOME"}, clear=True),
            patch("shutil.which", return_value=None),
            patch("os.path.exists", return_value=False),
        ):
            self.assertEqual(ag.detect_password_store(), "gnome-libsecret")

    def test_unknown_desktop_without_binaries_fallback(self):
        """On an unknown environment with no keyrings, returns basic."""
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("shutil.which", return_value=None),
            patch("os.path.exists", return_value=False),
        ):
            self.assertEqual(ag.detect_password_store(), "basic")


# ---------------------------------------------------------------------------
# Tests: update_argv_json
# ---------------------------------------------------------------------------


class TestUpdateArgvJson(unittest.TestCase):
    """Tests for ~/.<app>/argv.json update helper."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with
        self.home = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_creates_new_argv_json_when_missing(self):
        """Creates a new argv.json with password-store if file does not exist."""
        with patch.object(ag, "get_user_home", return_value=self.home):
            ag.update_argv_json("antigravity-ide", "gnome-libsecret")

        argv_file = os.path.join(self.home, ".antigravity-ide", "argv.json")
        self.assertTrue(os.path.exists(argv_file))
        with open(argv_file, "r", encoding="utf-8") as fh:
            content = fh.read()
        self.assertIn('"password-store": "gnome-libsecret"', content)

    def test_inserts_into_existing_argv_json(self):
        """Inserts password-store into existing argv.json containing other settings."""
        argv_dir = os.path.join(self.home, ".antigravity-ide")
        os.makedirs(argv_dir, exist_ok=True)
        argv_file = os.path.join(argv_dir, "argv.json")
        initial_content = '{\n\t// comment\n\t"enable-crash-reporter": true\n}'
        with open(argv_file, "w", encoding="utf-8") as fh:
            fh.write(initial_content)

        with patch.object(ag, "get_user_home", return_value=self.home):
            ag.update_argv_json("antigravity-ide", "gnome-libsecret")

        with open(argv_file, "r", encoding="utf-8") as fh:
            updated = fh.read()
        self.assertIn('"enable-crash-reporter": true', updated)
        self.assertIn('"password-store": "gnome-libsecret"', updated)

    def test_does_not_modify_if_password_store_already_present(self):
        """Leaves argv.json unchanged if password-store is already present."""
        argv_dir = os.path.join(self.home, ".antigravity-ide")
        os.makedirs(argv_dir, exist_ok=True)
        argv_file = os.path.join(argv_dir, "argv.json")
        initial_content = '{\n\t"password-store": "kwallet5"\n}'
        with open(argv_file, "w", encoding="utf-8") as fh:
            fh.write(initial_content)

        with patch.object(ag, "get_user_home", return_value=self.home):
            ag.update_argv_json("antigravity-ide", "gnome-libsecret")

        with open(argv_file, "r", encoding="utf-8") as fh:
            updated = fh.read()
        self.assertEqual(initial_content, updated)


# ---------------------------------------------------------------------------
# Tests: main CLI password store integration
# ---------------------------------------------------------------------------


class TestMainPasswordStore(unittest.TestCase):
    """Tests for password-store CLI argument injection in main()."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with
        self.home = self._tmp.name
        self.app_dir = os.path.join(self.home, ".local", "opt", "antigravity-ide")
        bin_path = os.path.join(self.app_dir, "antigravity-ide")
        _write(bin_path, "binary")
        _make_executable(bin_path)

    def tearDown(self):
        self._tmp.cleanup()

    def test_main_passes_detected_password_store(self):
        """main() appends --password-store=<store> to exec_args."""
        with (
            patch.object(sys, "argv", ["antigravity-ide"]),
            patch.object(ag, "get_user_home", return_value=self.home),
            patch.object(ag, "self_update"),
            patch.object(ag, "self_install"),
            patch.object(ag, "check_and_update"),
            patch.object(ag, "detect_password_store", return_value="gnome-libsecret"),
            patch("os.execv") as mock_execv,
        ):
            ag.main()

        mock_execv.assert_called_once()
        exec_args = mock_execv.call_args[0][1]
        self.assertIn("--password-store=gnome-libsecret", exec_args)

    def test_main_respects_user_supplied_password_store(self):
        """main() does not append duplicate flag if user already supplied --password-store."""
        with (
            patch.object(sys, "argv", ["antigravity-ide", "--password-store=basic"]),
            patch.object(ag, "get_user_home", return_value=self.home),
            patch.object(ag, "self_update"),
            patch.object(ag, "self_install"),
            patch.object(ag, "check_and_update"),
            patch.object(ag, "detect_password_store", return_value="gnome-libsecret"),
            patch("os.execv") as mock_execv,
        ):
            ag.main()

        mock_execv.assert_called_once()
        exec_args = mock_execv.call_args[0][1]
        self.assertIn("--password-store=basic", exec_args)
        self.assertNotIn("--password-store=gnome-libsecret", exec_args)


# ---------------------------------------------------------------------------
# Tests: Privileged mode / system installation
# ---------------------------------------------------------------------------


class TestPrivilegedMode(unittest.TestCase):
    """Tests for privileged / system-wide installation mode."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with
        self.home = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_can_use_sudo_as_root(self):
        """When running as root (uid 0), can_use_sudo returns True."""
        with patch("os.getuid", return_value=0):
            self.assertTrue(ag.can_use_sudo())

    def test_can_use_sudo_no_sudo_binary(self):
        """When sudo is not installed, can_use_sudo returns False."""
        with (
            patch("os.getuid", return_value=1000),
            patch("shutil.which", return_value=None),
        ):
            self.assertFalse(ag.can_use_sudo())

    def test_can_use_sudo_cached_or_passwordless(self):
        """When sudo -n true succeeds, can_use_sudo returns True."""
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        with (
            patch("os.getuid", return_value=1000),
            patch("shutil.which", return_value="/usr/bin/sudo"),
            patch("subprocess.run", return_value=mock_proc),
        ):
            self.assertTrue(ag.can_use_sudo())

    def test_can_use_sudo_fails_when_password_needed(self):
        """When sudo -n true fails, can_use_sudo returns False."""
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        with (
            patch("os.getuid", return_value=1000),
            patch("shutil.which", return_value="/usr/bin/sudo"),
            patch("subprocess.run", return_value=mock_proc),
        ):
            self.assertFalse(ag.can_use_sudo())

    def test_is_privileged_mode_env_user(self):
        """ANTIGRAVITY_INSTALL_MODE=user forces user mode."""
        with patch.dict(os.environ, {"ANTIGRAVITY_INSTALL_MODE": "user"}):
            self.assertFalse(ag.is_privileged_mode())

    def test_is_privileged_mode_env_system(self):
        """ANTIGRAVITY_INSTALL_MODE=system forces privileged mode."""
        with patch.dict(os.environ, {"ANTIGRAVITY_INSTALL_MODE": "system"}):
            self.assertTrue(ag.is_privileged_mode())

    def test_is_privileged_mode_cli_user(self):
        """Passing --user forces user mode."""
        with (
            patch.object(sys, "argv", ["antigravity", "--user"]),
            patch.object(ag, "can_use_sudo", return_value=True),
        ):
            self.assertFalse(ag.is_privileged_mode())

    def test_is_privileged_mode_cli_system(self):
        """Passing --system forces privileged mode."""
        with (
            patch.object(sys, "argv", ["antigravity", "--system"]),
            patch.object(ag, "can_use_sudo", return_value=False),
        ):
            self.assertTrue(ag.is_privileged_mode())

    def test_get_install_paths_privileged(self):
        """Privileged install paths target /opt and /usr/local."""
        paths = ag.get_install_paths(privileged=True)
        self.assertEqual(paths["opt_dir"], "/opt")
        self.assertEqual(paths["bin_dir"], "/usr/local/bin")
        self.assertEqual(paths["apps_dir"], "/usr/local/share/applications")
        self.assertTrue(paths["privileged"])

    def test_get_install_paths_user(self):
        """User install paths target ~/.local directories."""
        with patch.object(ag, "get_user_home", return_value=self.home):
            paths = ag.get_install_paths(privileged=False)
            self.assertEqual(paths["opt_dir"], os.path.join(self.home, ".local", "opt"))
            self.assertEqual(paths["bin_dir"], os.path.join(self.home, ".local", "bin"))
            self.assertFalse(paths["privileged"])

    def test_configure_chrome_sandbox_sets_suid_when_root(self):
        """configure_chrome_sandbox sets root ownership and 4755 when running as root."""
        app_dir = os.path.join(self.home, "app")
        sb_path = os.path.join(app_dir, "chrome-sandbox")
        _write(sb_path, "sandbox")

        with (
            patch("os.getuid", return_value=0),
            patch("os.chown") as mock_chown,
            patch("os.chmod") as mock_chmod,
        ):
            ag.configure_chrome_sandbox(app_dir)
            mock_chown.assert_called_once_with(sb_path, 0, 0)
            mock_chmod.assert_called_once_with(sb_path, 0o4755)

    def test_configure_chrome_sandbox_noop_when_not_root(self):
        """configure_chrome_sandbox does nothing when not running as root."""
        app_dir = os.path.join(self.home, "app")
        sb_path = os.path.join(app_dir, "chrome-sandbox")
        _write(sb_path, "sandbox")

        with (
            patch("os.getuid", return_value=1000),
            patch("os.chmod") as mock_chmod,
        ):
            ag.configure_chrome_sandbox(app_dir)
            mock_chmod.assert_not_called()

    def test_resolve_app_dir_prefers_opt(self):
        """resolve_app_dir returns /opt/<app> when executable is present there."""
        with patch.object(
            ag,
            "find_file_recursive",
            side_effect=lambda path, *args, **kwargs: (
                "/opt/antigravity/antigravity" if "/opt" in path else None
            ),
        ):
            self.assertEqual(ag.resolve_app_dir("antigravity"), "/opt/antigravity")

    def test_check_and_update_delegates_to_sudo_when_privileged_and_not_root(self):
        """check_and_update delegates update command to sudo when privileged and non-root."""
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        with (
            patch.object(
                ag,
                "get_install_paths",
                return_value={"privileged": True, "opt_dir": "/opt"},
            ),
            patch("os.getuid", return_value=1000),
            patch.object(ag, "can_use_sudo", return_value=True),
            patch("subprocess.run", return_value=mock_proc) as mock_run,
        ):
            ag.check_and_update("antigravity-ide", force=True)
            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]
            self.assertEqual(cmd[0], "sudo")
            self.assertIn("--internal-update=antigravity-ide", cmd)

    def test_check_and_update_skips_when_opt_installed_and_no_sudo(self):
        """When installed in /opt and user has no sudo, update is skipped."""
        with (
            patch.object(ag, "is_app_installed_in_opt", return_value=True),
            patch("os.getuid", return_value=1000),
            patch.object(ag, "can_use_sudo", return_value=False),
            patch.object(ag, "discover_download_url") as mock_discover,
        ):
            ag.check_and_update("antigravity")
            mock_discover.assert_not_called()

    def test_check_and_update_error_when_force_update_in_opt_and_no_sudo(self):
        """When installed in /opt, user has no sudo, and force=True, exits with error."""
        with (
            patch.object(ag, "is_app_installed_in_opt", return_value=True),
            patch("os.getuid", return_value=1000),
            patch.object(ag, "can_use_sudo", return_value=False),
        ):
            with self.assertRaises(SystemExit) as ctx:
                ag.check_and_update("antigravity", force=True)
            self.assertEqual(ctx.exception.code, 1)

    def test_resolve_app_dir_user_override(self):
        """Passing --user makes resolve_app_dir return ~/.local/opt even if /opt exists."""
        with (
            patch.object(sys, "argv", ["antigravity", "--user"]),
            patch.object(ag, "get_user_home", return_value=self.home),
            patch.object(
                ag, "find_file_recursive", return_value="/opt/antigravity/antigravity"
            ),
        ):
            self.assertEqual(
                ag.resolve_app_dir("antigravity"),
                os.path.join(self.home, ".local", "opt", "antigravity"),
            )

    def test_self_install_skips_when_opt_installed_and_no_sudo(self):
        """When app is installed in /opt and user has no sudo, self_install skips."""
        with (
            patch.object(ag, "is_app_installed_in_opt", return_value=True),
            patch("os.getuid", return_value=1000),
            patch.object(ag, "can_use_sudo", return_value=False),
            patch("shutil.copy2") as mock_copy,
        ):
            ag.self_install()
            mock_copy.assert_not_called()


if __name__ == "__main__":
    unittest.main()
