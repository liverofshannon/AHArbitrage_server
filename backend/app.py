"""AHarbitrage Flask 应用入口"""

import os
import secrets

from flask import Flask

from logger import log, log_request
from auth import auth_bp
from upload_api import upload_bp
from download_api import download_bp
from chart_api import chart_bp


def create_app():
    app = Flask(__name__)
    app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))
    app.before_request(log_request)
    app.register_blueprint(auth_bp)
    app.register_blueprint(upload_bp)
    app.register_blueprint(download_bp)
    app.register_blueprint(chart_bp)
    log.info(f"Flask 应用启动，ROOT_DIR={os.environ.get('ROOT_DIR', '/home/harry')}")
    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
