# D.M.S CENTRE - Game Top-Up Site
# Full Flask backend with Paystack integration + homepage route

from flask import Flask, request, jsonify, render_template
import uuid, datetime, requests, stripe

app = Flask(__name__)
orders = []

# ⚡ Your Paystack Keys (TEST mode for now)
PAYSTACK_SECRET = "sk_test_6e65ff4e63ac531551f4512fe421b1de1d4f0b7a"
PAYSTACK_PUBLIC = "pk_test_eb891946f3b430d306fa688bdd6cb1733754fca9"

# ⚡ Stripe keys (leave for later if not ready)
STRIPE_SECRET = "sk_test_xxx"
STRIPE_WEBHOOK_SECRET = "whsec_xxx"
stripe.api_key = STRIPE_SECRET

# Diamond pricing (NGN)
price_table = {
    100: 1000, 200: 2100, 300: 3200, 400: 4300, 500: 5400,
    600: 6500, 700: 7600, 800: 8700, 900: 10000, 1000: 14000,
    2000: 26000, 3000: 34000, 4000: 45000, 5000: 53000
}

products = [{"id": i+1, "game": "Free Fire", "diamonds": d, "price_ngn": p}
            for i, (d, p) in enumerate(price_table.items())]

# Convert price from NGN to other currencies
def convert_price(amount_ngn, target="NGN"):
    if target == "NGN":
        return amount_ngn, "NGN"
    try:
        url = f"https://api.exchangerate.host/convert?from=NGN&to={target}&amount={amount_ngn}"
        resp = requests.get(url).json()
        return round(resp["result"], 2), target
    except:
        return amount_ngn, "NGN"

# -------- ROUTES --------

@app.route("/")
def home():
    # Loads your homepage HTML from templates/index.html
    return render_template("index.html")

@app.route("/products")
def list_products():
    target = request.args.get("currency", "NGN").upper()
    return jsonify([{
        "id": p["id"],
        "game": p["game"],
        "diamonds": p["diamonds"],
        "price": convert_price(p["price_ngn"], target)[0],
        "currency": target
    } for p in products])

@app.route("/order", methods=["POST"])
def create_order():
    data = request.json
    product = next((x for x in products if x["id"] == data["product_id"]), None)
    if not product:
        return jsonify({"error": "Invalid product"}), 400

    price, curr = convert_price(product["price_ngn"], data.get("currency", "NGN"))
    order_id = str(uuid.uuid4())
    order = {
        "id": order_id,
        "game": product["game"],
        "diamonds": product["diamonds"],
        "player_id": data["player_id"],
        "currency": curr,
        "price": price,
        "status": "pending",
        "created_at": datetime.datetime.utcnow().isoformat()
    }
    orders.append(order)

    # -------- Payment Handling --------
    if curr == "NGN":
        # Paystack
        headers = {"Authorization": f"Bearer {PAYSTACK_SECRET}", "Content-Type": "application/json"}
        payload = {
            "email": data.get("email", "user@example.com"),
            "amount": int(product["price_ngn"] * 100),  # amount in kobo
            "currency": "NGN",
            "reference": order_id,
            "callback_url": "https://yourdomain.com/payment/callback"
        }
        r = requests.post("https://api.paystack.co/transaction/initialize", json=payload, headers=headers)
        res = r.json()
        order["payment_link"] = res["data"]["authorization_url"] if res.get("status") else "error"
    else:
        # Stripe
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": curr.lower(),
                    "product_data": {"name": f"{product['diamonds']} Diamonds"},
                    "unit_amount": int(price * 100),
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url="https://yourdomain.com/success?session_id={CHECKOUT_SESSION_ID}",
            cancel_url="https://yourdomain.com/cancel",
            metadata={"order_id": order_id}
        )
        order["payment_link"] = session.url

    return jsonify(order)

@app.route("/orders")
def list_orders():
    return jsonify(orders)

# -------- WEBHOOKS --------

@app.route("/webhook/paystack", methods=["POST"])
def paystack_webhook():
    data = request.json
    if data.get("event") == "charge.success":
        ref = data["data"]["reference"]
        for o in orders:
            if o["id"] == ref:
                o["status"] = "paid"
                o["paid_at"] = datetime.datetime.utcnow().isoformat()
                return jsonify({"ok": True})
    return jsonify({"ok": False})

@app.route("/webhook/stripe", methods=["POST"])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature")
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        oid = session["metadata"]["order_id"]
        for o in orders:
            if o["id"] == oid:
                o["status"] = "paid"
                o["paid_at"] = datetime.datetime.utcnow().isoformat()
    return jsonify({"ok": True})

if __name__ == "__main__":
    app.run(debug=True, port=5000)