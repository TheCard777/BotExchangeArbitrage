"""The bot must expose a version string, surfaced at startup so a screenshot
immediately shows which build is running."""
import re

import bot


def test_version_is_a_sane_string():
    assert isinstance(bot.__version__, str)
    assert re.match(r"^\d+\.\d+\.\d+$", bot.__version__)
