# Contributing

Thank you for helping improve `healthpixel-audit`.

- **Vendor rules** live in `healthpixel_audit/vendors.py`, **condition and treatment terms** in `healthpixel_audit/terms.py`. They are plain Python lists; a pull request that adds a vendor or a term should include a test in `tests/` with a real-looking request or page title.
- **Bugs**: open an issue with the command you ran, the output, and your Python and Playwright versions. Do not paste raw request logs: they can contain your browser's cookie IDs.
- **Security problems**: do not open an issue; see [SECURITY.md](SECURITY.md).
- Before sending a pull request, run the tests:

```bash
python -m pip install ".[test]"
python -m pytest tests
```

Keep changes small and focused. By contributing you agree that your contribution is licensed under the MIT licence of this project.
