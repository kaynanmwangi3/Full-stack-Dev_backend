from flask import Flask, request, jsonify
from flask_cors import CORS
from models import db, User, Post
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import datetime
from flask_migrate import Migrate
import os, re, time

app = Flask(__name__)
base_dir = os.path.abspath(os.path.dirname(__file__))
db_file = os.path.join(base_dir, "users.db")
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_file}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["JSON_SORT_KEYS"] = False

# Allow dev origins -- during dev you can use CORS(app) or specify ports
# CORS(app, resources={r"/api/*": {"origins": "https://full-stack-dev-rho.vercel.app"}})
frontend_url = os.environ.get('FRONTEND_URL', 'https://full-stack-dev-rho.vercel.app')

CORS(app, resources={r"/api/*": {
    "origins": [
        frontend_url,
        "http://localhost:5173", 
        "http://127.0.0.1:5173"
    ],
    "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    "allow_headers": ["Content-Type", "Authorization"]
}})

@app.before_request
def handle_preflight():
    if request.method == "OPTIONS":
        response = jsonify()
        response.headers.add("Access-Control-Allow-Origin", frontend_url)
        response.headers.add("Access-Control-Allow-Headers", "Content-Type, Authorization")
        response.headers.add("Access-Control-Allow-Methods", "GET, PUT, POST, DELETE, OPTIONS")
        response.headers.add("Access-Control-Allow-Credentials", "true")
        return response

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', frontend_url)
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    response.headers.add('Access-Control-Allow-Credentials', 'true')
    return response
db.init_app(app)

migrate = Migrate(app, db)


@app.route("/api/register", methods=["POST"])
def register():
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    if not (name and email and password):
        return jsonify({"success": False, "message": "name, email and password are required"}), 400

    # check existing username/email
    if User.query.filter((User.name == name) | (User.email == email)).first():
        return jsonify({"success": False, "message": "username or email already exists"}), 409

    pw_hash = generate_password_hash(password)
    user = User(name=name, email=email, password_hash=pw_hash)
    db.session.add(user)
    db.session.commit()

    return jsonify({"success": True, "message": "registered successfully", "user": user.to_dict()}), 201

@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    password = data.get("password", "")

    if not (name and password):
        return jsonify({"success": False, "message": "name and password are required"}), 400

    user = User.query.filter_by(name=name).first()
    if not user or not check_password_hash(user.password_hash, password):
        # exactly the text you asked for
        return jsonify({"success": False, "message": "either username or password is wrong"}), 401

    # simple success response; in production return a token
    return jsonify({"success": True, "message": "login successful", "user": user.to_dict(), "user_id": user.id}), 200

@app.route("/api/users/<int:user_id>", methods=["PUT"])
def update_user(user_id):
    # Get the user to update
    user = User.query.get(user_id)
    if not user:
        return jsonify({"success": False, "message": "user not found"}), 404

    data = request.get_json() or {}
    
    # Check if new name is provided and if it's already taken by another user
    new_name = data.get("name")
    if new_name and new_name != user.name:
        existing_user = User.query.filter_by(name=new_name).first()
        if existing_user and existing_user.id != user_id:
            return jsonify({"success": False, "message": "username already taken"}), 409
        user.name = new_name

    # Check if new email is provided and if it's already taken by another user
    new_email = data.get("email")
    if new_email and new_email != user.email:
        existing_user = User.query.filter_by(email=new_email).first()
        if existing_user and existing_user.id != user_id:
            return jsonify({"success": False, "message": "email already taken"}), 409
        user.email = new_email

    # Update password if provided
    new_password = data.get("password")
    if new_password:
        user.password_hash = generate_password_hash(new_password)

    try:
        db.session.commit()
        return jsonify({
            "success": True, 
            "message": "user updated successfully",
            "user": user.to_dict()
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": "error updating user"}), 500

@app.route("/api/posts", methods=["GET", "POST"])
def posts():
    if request.method == "GET":
        posts = Post.query.order_by(Post.created_at.desc()).all()
        return jsonify([p.to_dict() for p in posts]), 200

    # POST -> create a post
    data = request.get_json() or {}
    title = data.get("title", "").strip()
    content = data.get("content", "").strip()
    image_url = data.get("image_url")
    author_id = data.get("author_id")  # frontend should send integer user id

    if not (title and content and author_id):
        return jsonify({"success": False, "message": "title, content and author_id are required"}), 400

    user = User.query.get(author_id)
    if not user:
        return jsonify({"success": False, "message": "author not found"}), 404


    post = Post(
        title=title,
        content=content,
        image_url=image_url,
        author_id=author_id
    )
    db.session.add(post)
    db.session.commit()
    return jsonify({"success": True, "post": post.to_dict()}), 201

# single post get/update/delete
@app.route("/api/posts/<int:post_id>", methods=["GET", "PUT", "DELETE"])
def single_post(post_id):
    post = Post.query.get(post_id)
    if not post:
        return jsonify({"success": False, "message": "post not found"}), 404

    if request.method == "GET":
        return jsonify(post.to_dict()), 200

    if request.method == "PUT":
        data = request.get_json() or {}
        # simple ownership check: require author_id match or skip for now
        title = data.get("title")
        content = data.get("content")
        image_url = data.get("image_url")
        author_id = data.get("author_id")

        if title:
            post.title = title
        if content:
            post.content = content
        if image_url is not None:
            post.image_url = image_url
        if author_id:
            author_id = author_id

        db.session.commit()
        return jsonify({"success": True, "post": post.to_dict()}), 200

    # DELETE
    db.session.delete(post)
    db.session.commit()
    return jsonify({"success": True, "message": "deleted"}), 200

# posts by user
@app.route("/api/users/<int:user_id>/posts", methods=["GET"])
def posts_by_user(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"success": False, "message": "user not found"}), 404
    posts = Post.query.filter_by(author_id=user_id).order_by(Post.created_at.desc()).all()
    return jsonify([p.to_dict() for p in posts]), 200


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
