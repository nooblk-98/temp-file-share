# Contribution Guide

Thanks for contributing! This project focuses on a simple, reliable upload service. Please keep changes small and focused.

## How to Contribute

1. Fork the repository.
2. Create a feature branch.
3. Make your changes with clear commit messages.
4. Open a pull request describing the change and rationale.

## Code Style

- Keep Python changes minimal and readable.
- Prefer small functions over long blocks.
- Avoid adding heavy dependencies.

## Testing

- For backend changes, run the service and validate:
  - Upload flow (`POST /upload` via `upload.sh`).
  - Download flow (`GET /download/<filename>`).
  - Clear flow (`POST /clear`).
- For UI changes, open the homepage and confirm it renders correctly.

## Security Notes

- Do not add authentication without discussing the scope and desired flow.
- Avoid logging sensitive data.

## Documentation

- Update `README.md` for user-facing changes.
- Update `DEVELOPMENT.md` for developer-facing changes.
