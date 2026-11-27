"""Nos testes a API nunca le a planilha real (leva ~15 s): usa os dados falsos."""

import os

os.environ.setdefault("CAGED_USE_FAKE", "1")
