import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app


class AppTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root_patch = patch.object(app, "ROOT", Path(self.folder.name) / "new" / "workspace")
        self.root_patch.start()
        self.ui = app.App()
        self.ui.withdraw()
        self.ui.update()

    def tearDown(self):
        for callback in self.ui.tk.call("after", "info"):
            self.ui.after_cancel(callback)
        self.ui.destroy()
        self.root_patch.stop()
        self.folder.cleanup()

    def test_first_start_creates_nested_workspace(self):
        self.assertTrue((app.ROOT / "input_audio").is_dir())
        self.assertTrue((app.ROOT / "output_text").is_dir())
        self.assertEqual(self.ui.input_dir.get(), "input_audio")

    def test_cancel_completion_restores_controls(self):
        self.ui.busy = True
        self.ui.cancel_button.configure(state="normal")
        for widget in self.ui.controls:
            widget.configure(state="disabled")
        self.ui.cancel()
        self.assertTrue(self.ui.cancelled.is_set())
        self.ui.events.put(("done", (0, [], ["md"], True)))
        self.ui.poll()
        self.assertFalse(self.ui.busy)
        self.assertIn("Cancelled", self.ui.status.get())
        self.assertTrue(self.ui.cancel_button.instate(["disabled"]))
        self.assertTrue(all(not widget.instate(["disabled"]) for widget in self.ui.controls))

    def test_close_while_busy_requests_cancellation(self):
        self.ui.busy = True
        with patch.object(app.messagebox, "askyesno", return_value=True):
            self.ui.close()
        self.assertTrue(self.ui.closing)
        self.assertTrue(self.ui.cancelled.is_set())
