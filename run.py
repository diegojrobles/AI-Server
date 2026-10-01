from app.server import app
from config.settings import settings

if __name__ == "__main__":
    app.run(host=settings.host, port=settings.port, debug=settings.debug)
