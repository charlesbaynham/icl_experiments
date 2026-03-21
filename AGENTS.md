# AGENTS.md - Notes for AI Assistants

## Repository Rules

### Aravis Directory - DO NOT MODIFY

**The `nix/aravis/` directory contains third-party code that is NOT controlled by this repository.**

- Do NOT fix FIXMEs or TODOs in this directory
- Do NOT modify any files under `nix/aravis/`
- This is external/vendor code - any changes would be overwritten or lost

### FIXME Handling

- FIXME markers in this codebase will fail CI (per `.github/copilot-instructions.md`)
- When asked to fix FIXMEs, search the entire codebase but exclude `nix/aravis/`
- The actual project code is under `repository/` and `tests/`

### Common Directories

- `repository/` - Main project code
- `tests/` - Test files
- `nix/aravis/` - **EXTERNAL - DO NOT MODIFY**
