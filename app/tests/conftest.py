import sys
from unittest.mock import MagicMock

# 1. Fake the AI Libraries
# When the code says "import whisper", Python will return this fake object instead.
sys.modules["whisper"] = MagicMock()
sys.modules["transformers"] = MagicMock()
sys.modules["torch"] = MagicMock()

# 2. Fake Celery
# We don't want the background worker trying to connect to a real message broker
sys.modules["celery"] = MagicMock()
sys.modules["celery_app"] = MagicMock()