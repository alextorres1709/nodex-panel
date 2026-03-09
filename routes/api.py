from flask import Blueprint, jsonify
from config import APP_VERSION

api_bp = Blueprint("api", __name__)

DOWNLOAD_URL = "https://github.com/alextorres1709/nodex-panel/releases/latest/download/NodexAI-Panel.dmg"


@api_bp.route("/api/version")
def version():
    return jsonify({
        "version": APP_VERSION,
        "download_url": DOWNLOAD_URL,
    })
