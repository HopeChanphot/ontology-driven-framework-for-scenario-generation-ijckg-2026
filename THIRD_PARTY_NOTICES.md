# Third-party portable runtime notices

The separate continuation package may include third-party installers, runtime
software, Python wheels, and an open-weight model solely to make the macOS
smoke workflow copyable and locally runnable. These large assets are not
stored in this GitHub repository.

## Bundled small model

- Model: Qwen2.5-0.5B-Instruct GGUF
- Quantization: Q4_0
- Upstream: `Qwen/Qwen2.5-0.5B-Instruct-GGUF`
- Portable-bundle filename: `models/qwen2.5-0.5b-instruct-q4_0.gguf`
- Expected upstream SHA-256:
  `7671c0c304e6ce5a7fc577bcb12aba01e2c155cc2efd29b2213c95b18edaf6ed`
- License: Apache License 2.0

The 0.5B model is for low-resource integration smoke testing. It is not one of
the frozen paper models and must not replace or reinterpret the reported paper
experiment.

## Ollama

- Portable-bundle release: v0.30.8 macOS
- Filename: `runtime/Ollama-darwin-v0.30.8.zip`
- Expected upstream SHA-256:
  `62a68eacb27dde8d61560fd3bf4c5669c141f5482c5668ce7328420e871088e6`
- License: MIT
- macOS requirement: macOS 14 Sonoma or newer

## Python

- Portable-bundle installer: Python 3.12.10 macOS universal2
- Filename: `runtime/python-3.12.10-macos11.pkg`
- Source: Python Software Foundation

## Python wheels

The separate portable bundle contains dependency wheelhouses resolved from
`requirements-macos.txt` for CPython 3.12:

- `wheelhouse/macos-arm64/`
- `wheelhouse/macos-x86_64/`

Third-party names and trademarks remain the property of their respective
owners. Review institutional redistribution requirements before distributing
the complete portable bundle beyond the internship handover group.
