import logging
from flask import Flask, jsonify
from flask_cors import CORS
from flask import render_template

app = Flask(__name__)
CORS(app)

@app.route("/")
def index():
    """Головна сторінка з HTML інтерфейсом"""
    return render_template("index.html")


if __name__ == "__main__":
    app.run()
