import os
import sqlite3
import uuid
from flask import Flask, jsonify, request

app = Flask(__name__)

# ডাটাবেজ ফাইল লিংক
DB_PATH = os.path.join(os.path.dirname(__file__), "newbot.db")
API_KEY = "YOUR_SECRET_API_KEY"  # নিজের পছন্দমতো একটি সিক্রেট কি (Key) দিন


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# অথেন্টিকেশন চেক
def check_auth():
    key = request.headers.get("X-API-Key")
    return key == API_KEY


@app.route("/balance", methods=["GET"])
def get_balance():
    if not check_auth():
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    with get_db() as conn:
        # আপনার বটের এডমিন বা নির্দিষ্ট ইউজার ব্যালেন্স দেখতে
        user = conn.execute("SELECT balance FROM users LIMIT 1").fetchone()
        bal = user["balance"] if user else 0.0

    return jsonify({"success": True, "balance": bal, "currency": "USD"})


@app.route("/products", methods=["GET"])
def get_products():
    if not check_auth():
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    with get_db() as conn:
        products = conn.execute(
            """
            SELECT p.id, p.name, p.description, p.price,
                   (SELECT COUNT(*) FROM stock s WHERE s.product_id = p.id AND s.is_sold = 0) as available
            FROM products p
            WHERE p.is_active = 1
        """
        ).fetchall()

    res = [
        {
            "id": p["id"],
            "name": p["name"],
            "description": p["description"] or "",
            "price": float(p["price"]),
            "available": p["available"],
        }
        for p in products
    ]
    return jsonify({"success": True, "products": res})


@app.route("/orders", methods=["GET"])
def get_orders():
    if not check_auth():
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    with get_db() as conn:
        orders = conn.execute(
            """
            SELECT id, product_id, amount, status, created_at 
            FROM orders ORDER BY created_at DESC LIMIT 20
        """
        ).fetchall()

    res = [
        {
            "id": o["id"],
            "product_id": o["product_id"],
            "amount": float(o["amount"]),
            "status": o["status"],
            "created_at": o["created_at"],
        }
        for o in orders
    ]
    return jsonify({"success": True, "orders": res})


@app.route("/order", methods=["POST"])
def create_order():
    if not check_auth():
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    data = request.get_json() or {}
    product_id = data.get("product_id")
    quantity = data.get("quantity", 1)

    if not product_id:
        return jsonify({"success": False, "message": "product_id required"}), 400

    with get_db() as conn:
        # স্টক চেক
        stocks = conn.execute(
            "SELECT id, content FROM stock WHERE product_id=? AND is_sold=0 LIMIT ?",
            (product_id, quantity),
        ).fetchall()

        if len(stocks) < quantity:
            return jsonify({"success": False, "message": "Out of stock"}), 400

        product = conn.execute(
            "SELECT price FROM products WHERE id=?", (product_id,)
        ).fetchone()
        price = float(product["price"]) * quantity

        # ডেলিভারি ও স্টক মার্ক করা
        order_id = "ORD-" + uuid.uuid4().hex[:10].upper()
        delivery_items = []
        for s in stocks:
            delivery_items.append(s["content"])
            conn.execute(
                "UPDATE stock SET is_sold=1, sold_at=datetime('now') WHERE id=?",
                (s["id"],),
            )

        conn.execute(
            "INSERT INTO orders(id, user_id, product_id, stock_id, amount, status, created_at) VALUES(?, ?, ?, ?, ?, 'completed', datetime('now'))",
            (order_id, 0, product_id, stocks[0]["id"], price),
        )
        conn.commit()

    return jsonify(
        {
            "success": True,
            "order_id": order_id,
            "product_id": product_id,
            "quantity": quantity,
            "amount": price,
            "delivery": delivery_items,
        }
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8787)
