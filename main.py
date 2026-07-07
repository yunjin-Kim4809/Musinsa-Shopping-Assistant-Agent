"""하위 호환 진입점.

기존 사용법(python main.py)을 유지한다. 실제 구현은 app 패키지에 있다.
- CLI:      python main.py        (== python -m app.cli)
- API 서버: python -m app.api     (== uvicorn "app.api.app:create_app" --factory)
"""

from app.cli import main

if __name__ == "__main__":
    main()
