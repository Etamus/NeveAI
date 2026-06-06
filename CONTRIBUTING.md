# Contributing to NeveAI

Thank you for your interest in contributing to NeveAI!

NeveAI is a local-first, privacy-focused AI platform built around FastAPI, SvelteKit, llama.cpp, GGUF models, hybrid RAG, Pyodide-based code execution, and offline-first workflows. Contributions of all kinds are welcome, whether you are fixing bugs, improving documentation, testing hardware setups, refining the interface, or proposing new features.

## Ways to Contribute

You can help NeveAI in many ways:

* **Report Bugs**: Open an issue when something is not working as expected.
* **Suggest Features**: Share ideas that improve local AI workflows, privacy, usability, performance, or model support.
* **Improve Documentation**: Help make setup, usage, troubleshooting, and development instructions clearer.
* **Fix Issues**: Submit pull requests that resolve bugs, improve stability, or simplify the codebase.
* **Improve the Frontend**: Work on the SvelteKit interface, components, layout, accessibility, or user experience.
* **Improve the Backend**: Work on FastAPI routes, WebSocket behavior, RAG, model loading, database logic, or local tooling.
* **Test Hardware Support**: Help test NVIDIA, AMD, Vulkan, ROCm, or CPU-only setups.
* **Share Feedback**: Tell us how NeveAI behaves on your machine and what could be improved.

Even small contributions are valuable. A clear bug report, a typo fix, a screenshot, or a tested reproduction can save a lot of time.

## Before You Start

Before opening an issue or pull request:

1. Search existing issues and pull requests to avoid duplicates.
2. Make sure your local copy is up to date with the `main` branch.
3. Keep your changes focused on a single topic whenever possible.
4. Avoid committing generated files, local data, models, logs, virtual environments, or private configuration files.

## Development Requirements

NeveAI is primarily developed for Windows.

Recommended requirements:

* Python 3.11 or 3.12
* Node.js 18 or newer
* Git
* PowerShell
* A compatible GPU is recommended, but CPU-only testing is also useful
* Internet access during installation only

Linux and macOS may require adaptations. Contributions that improve cross-platform support are welcome, but please clearly describe the operating system and environment used for testing.

## Project Setup

Clone the repository:

```bash
git clone https://github.com/Etamus/NeveAI.git
cd NeveAI
```

On Windows, run the installer:

```bat
instalar.bat
```

The installer prepares the Python environment, installs Node.js dependencies, downloads required llama.cpp binaries, builds the frontend, creates runtime folders, and prepares the default configuration.

After installation, start NeveAI with:

```bat
iniciar.bat
```

By default, NeveAI runs on:

```text
http://localhost:8080
```

## Development Mode

For development with hot reload, run the backend and frontend separately.

### Backend

```powershell
cd "c:\Neve AI\backend"
..\backend\neveai\venv\Scripts\python -m uvicorn neveai.main:app --host 0.0.0.0 --port 8080 --reload
```

### Frontend

```powershell
cd "c:\Neve AI"
npm run dev
```

The development frontend is available at:

```text
http://localhost:5173
```

The frontend development server proxies requests to the backend running on port `8080`.

## Building the Project

To build the frontend manually:

```powershell
npm run build
```

Then copy the generated frontend build to the backend frontend directory:

```powershell
Copy-Item -Path "build\*" -Destination "backend\neveai\frontend" -Recurse -Force
```

You can also use the provided build scripts when available:

```bat
buildar.bat
```

## Code Style

Please keep the codebase clean, readable, and consistent with the existing style.

For frontend changes:

```bash
npm run check
npm run lint:frontend
npm run format
```

For backend changes:

```bash
npm run lint:backend
npm run format:backend
```

Before submitting a pull request, run the checks that are relevant to the files you changed.

## What Not to Commit

Do not commit local runtime files, generated folders, private configuration, downloaded models, or machine-specific data.

Avoid committing:

```text
.env
backend/neveai/venv/
backend/neveai/frontend/
backend/neveai/data/
backend/data/
models/
mmproj/
llamacpp-server/
node_modules/
build/
logs/
.svelte-kit/
```

If your change requires modifying generated output, explain why in the pull request.

## Reporting Bugs

When reporting a bug, please include as much useful information as possible.

A good bug report should include:

* A clear title
* A short explanation of what happened
* What you expected to happen
* Steps to reproduce the issue
* Your operating system
* Python version
* Node.js version
* GPU model, if relevant
* Whether you are using CUDA, Vulkan, ROCm, or CPU
* The model format and type, if model-related
* Screenshots, logs, or traceback output when available

Please remove private information from logs before posting them publicly.

## Suggesting Features

Feature requests are welcome.

When suggesting a feature, please describe:

* The problem you are trying to solve
* Why the feature would be useful for NeveAI users
* How you imagine the feature working
* Any alternatives you considered
* Whether the feature should work fully offline

Because NeveAI is focused on local-first and privacy-first AI, features that require external services, cloud APIs, telemetry, or third-party accounts should be clearly explained and optional.

## Pull Request Guidelines

When submitting a pull request:

1. Fork the repository.
2. Create a new branch with a descriptive name.
3. Keep your changes focused and easy to review.
4. Update documentation when behavior changes.
5. Test your changes locally.
6. Do not include unrelated formatting changes.
7. Do not commit generated files or local machine data.
8. Explain what changed and why.

Example branch names:

```text
fix/model-loading-error
feature/rag-source-preview
docs/improve-windows-setup
ui/chat-message-actions
```

## Pull Request Checklist

Before opening a pull request, please check that:

* The project builds successfully.
* Relevant frontend or backend checks were run.
* The change was tested locally.
* Documentation was updated if needed.
* No private files, models, logs, or generated folders were committed.
* The pull request description clearly explains the change.
* Screenshots or recordings are included for UI changes when helpful.

## Documentation Contributions

Documentation improvements are highly appreciated.

You can help by improving:

* Installation instructions
* Windows setup notes
* GPU setup notes
* Model and `mmproj` usage
* RAG documentation
* Troubleshooting guides
* Screenshots and examples
* Developer workflow instructions

Please keep documentation practical, direct, and easy to follow.

## Security and Privacy

NeveAI is designed around local execution and data sovereignty. Contributions should respect that goal.

Please avoid adding features that:

* Send user data to external services without clear consent
* Require cloud APIs for core functionality
* Add telemetry by default
* Expose local files, prompts, conversations, or model data
* Store secrets in source code
* Log sensitive user data unnecessarily

If you discover a security issue, please do not open a public issue with exploit details. Contact the project maintainer privately instead.

## Community Standards

Please be respectful and constructive in all interactions.

By participating in this project, you agree to follow the project's Code of Conduct:

```text
https://github.com/Etamus/NeveAI/blob/main/CODE_OF_CONDUCT.md
```

## Thank You

Thank you for helping improve NeveAI.

Whether your contribution is code, testing, documentation, feedback, or simply sharing the project, it helps make local-first AI more accessible, private, and powerful for everyone.
