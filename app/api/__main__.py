"""`python -m app.api` 로 개발 서버를 띄운다."""

import uvicorn


def main() -> None:
    uvicorn.run("app.api.app:create_app", factory=True, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
