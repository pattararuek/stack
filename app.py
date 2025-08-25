from flask import Flask, request, jsonify
from flask_cors import CORS
import yfinance as yf
import random
import json
from collections import Counter
import hashlib

app = Flask(__name__)
CORS(app)

# โหลดไฟล์หุ้น
with open("lotto_stocks.json", encoding="utf-8") as f:
    STOCKS = json.load(f)

def stable_random(symbol, mins):
    """สุ่มแบบคงที่ (seed คงที่) เพื่อให้กดกี่ครั้งก็ได้ค่าเดิม"""
    seed = int(hashlib.sha256(f"{symbol}-{mins}".encode()).hexdigest(), 16) % (10**8)
    rnd = random.Random(seed)
    return rnd.uniform(-0.003, 0.003)  # ±0.3%

def make_lotto(price, change):
    """
    สูตรหวยหุ้น:
      - 3 ตัวบน = 3 หลักท้ายของราคา (รวมทศนิยม)
      - 2 ตัวบน = ทศนิยม 2 หลักของราคา
      - 2 ตัวล่าง = ทศนิยม 2 หลักของ "ผลต่างจากราคาปิดก่อนหน้า"
    """
    price_str = f"{price:.2f}"
    change_str = f"{abs(change):.2f}"

    three_top = price_str.replace(".", "")[-3:]
    two_top = price_str.split(".")[1]
    two_bottom = change_str.split(".")[1]

    return {
        "threeTop": three_top,
        "twoTop": two_top,
        "twoBottom": two_bottom
    }

def format_counter(counter, top_n=None):
    """แปลง Counter -> list เรียงจากมากไปน้อย"""
    items = counter.most_common()
    if top_n:
        items = items[:top_n]
    return [f"{digit} ({count} ครั้ง)" for digit, count in items]

@app.route("/search")
def search():
    q = request.args.get("q", "").lower()
    if not q:
        return jsonify([])
    results = []
    for s in STOCKS:
        if q in s["symbol"].lower() or q in s["name"].lower() or q in s["thai"].lower():
            results.append(s)
    return jsonify(results[:20])

@app.route("/quote")
def quote():
    symbol = request.args.get("symbol")
    if not symbol:
        return jsonify({"error": "กรุณาระบุ symbol"})

    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        last_price = info.get("regularMarketPrice")
        prev_close = info.get("regularMarketPreviousClose")

        if last_price is None or prev_close is None:
            return jsonify({"error": f"ไม่พบข้อมูลของ {symbol}"})

        change = last_price - prev_close
        percent_change = (change / prev_close) * 100 if prev_close else 0

        data = {
            "symbol": symbol,
            "price": round(last_price, 2),
            "change": round(change, 2),
            "percentChange": round(percent_change, 2),
            "lotto": make_lotto(last_price, change),
            "forecast": {},
            "probability": {},
            "summary": {}
        }

        three_digits, two_top_digits, two_bottom_digits = [], [], []

        # ✅ รวมปัจจุบันด้วย
        current_lotto = make_lotto(last_price, change)
        three_digits.extend(list(current_lotto["threeTop"]))
        two_top_digits.extend(list(current_lotto["twoTop"]))
        two_bottom_digits.extend(list(current_lotto["twoBottom"]))

        # ✅ forecast (สุ่มคงที่)
        for mins in [5, 10, 15, 20, 25, 30]:
            factor = stable_random(symbol, mins)
            f_price = last_price * (1 + factor)
            f_change_from_prev = f_price - prev_close
            f_percent_change = (f_change_from_prev / prev_close) * 100 if prev_close else 0

            lotto = make_lotto(round(f_price, 2), round(f_change_from_prev, 2))
            data["forecast"][f"{mins}m"] = {
                "price": round(f_price, 2),
                "change": round(f_change_from_prev, 2),
                "percentChange": round(f_percent_change, 2),
                "lotto": lotto
            }

            three_digits.extend(list(lotto["threeTop"]))
            two_top_digits.extend(list(lotto["twoTop"]))
            two_bottom_digits.extend(list(lotto["twoBottom"]))

        # ✅ นับความถี่
        c3 = Counter(three_digits)
        c2t = Counter(two_top_digits)
        c2b = Counter(two_bottom_digits)

        data["probability"] = {
            "threeTop": dict(c3.most_common()),
            "twoTop": dict(c2t.most_common()),
            "twoBottom": dict(c2b.most_common())
        }

        # ✅ สรุป Top 3 / Top 2
        data["summary"] = {
            "threeTop": format_counter(c3, 3),
            "twoTop": format_counter(c2t, 2),
            "twoBottom": format_counter(c2b, 2)
        }

        return jsonify(data)

    except Exception as e:
        return jsonify({"error": str(e)})

if __name__ == "__main__":
    app.run(debug=True)
