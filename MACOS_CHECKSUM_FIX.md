# macOS checksum-copy fix

The bundled model is working if Terminal prints:

```text
Bundled small-LLM integration passed.
```

Older copies of the portable package can stop at package verification because:

- macOS Finder creates `.DS_Store` files; and
- some transfer methods omit the development-only `.gitignore` and
  `.gitattributes` files.

Package version 1.1 ignores operating-system metadata and does not require
those two development-only dotfiles.

## Preferred fix

Replace these three files with the newest versions:

```text
tools/package_integrity.py
MANIFEST.csv
CHECKSUMS_SHA256.txt
```

Then open Terminal, enter the project folder, and run each command separately:

```bash
cd /path/to/interjp
chmod +x START_AND_TEST_MACOS.command RUN_AND_TEST_MACOS.sh
./START_AND_TEST_MACOS.command
```

The model and private runtime already created inside `.portable_runtime` will
be reused.

## Immediate workaround for an older copy

If the updated files are not yet available, run:

```bash
cd /path/to/interjp
find . -name '.DS_Store' -type f -delete
.venv/bin/python tools/package_integrity.py generate
./START_AND_TEST_MACOS.command
```

This rebuilds the manifest for the transferred Mac copy. Use this workaround
only when the preceding verifier output reports no missing project files other
than `.gitignore` and `.gitattributes`.

## Avoid malformed pasted commands

Do not paste text containing `<2028>`. It represents an invisible Unicode line
separator and makes the shell treat several commands as arguments to `ls`.
Press Return after each command or paste the three-line code block above as
plain text.
