import os
import base64
from flask import Flask, request, jsonify, render_template_string
import google.generativeai as genai

app = Flask(__name__)

genai.configure(api_key=os.environ.get("GEMINI_API_KEY").strip())
model = genai.GenerativeModel("models/gemini-1.5-flash")

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <title>Bid Bond Validator</title>
    <style>
        body { font-family: sans-serif; background: #f4f7f9; display: flex; justify-content: center; padding: 20px; text-align: right; }
        .card { background: white; padding: 30px; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.1); width: 100%; max-width: 600px; }
        h2 { color: #d93025; text-align: center; border-bottom: 2px solid #eee; padding-bottom: 15px; }
        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-bottom: 15px; }
        label { display: block; margin-bottom: 5px; font-weight: bold; }
        input, select { width: 100%; padding: 12px; border: 1px solid #ccc; border-radius: 8px; box-sizing: border-box; }
        button { width: 100%; background: #1a73e8; color: white; padding: 15px; border: none; border-radius: 8px; margin-top: 25px; cursor: pointer; font-weight: bold; font-size: 16px; }
        button:disabled { background: #aaa; cursor: not-allowed; }
        #status { display: none; text-align: center; margin: 20px 0; color: #1a73e8; font-weight: bold; }
        #report { margin-top: 20px; padding: 15px; background: #fafafa; border: 1px solid #ddd; border-radius: 8px; display: none; }
        #report table { width: 100%; border-collapse: collapse; }
        #report th { background: #1a73e8; color: white; padding: 8px; }
        #report td { padding: 8px; border: 1px solid #ddd; }
    </style>
</head>
<body>
    <div class="card">
        <h2>منصة تدقيق خطابات الضمان</h2>
        <div class="grid">
            <div><label>Tender No:</label><input type="text" id="tNum" placeholder="HFY-CON/F&C..."></div>
            <div><label>Tender Name:</label><input type="text" id="tName" placeholder="اسم المناقصة"></div>
        </div>
        <div class="grid">
            <div>
                <label>Bid Bond Amount (USD):</label>
                <select id="bAmount">
                    <option value="2500">2,500</option>
                    <option value="7000">7,000</option>
                    <option value="20000">20,000</option>
                    <option value="60000">60,000</option>
                    <option value="120000" selected>120,000</option>
                    <option value="200000">200,000</option>
                    <option value="500000">500,000</option>
                    <option value="1000000">1,000,000</option>
                    <option value="2000000">2,000,000</option>
                </select>
            </div>
            <div><label>Bid Closing Date:</label><input type="date" id="cDate"></div>
        </div>
        <label>رفع ملف PDF:</label>
        <input type="file" id="fileInput" accept=".pdf">
        <button id="runBtn" onclick="process()">تحليل المستند</button>
        <div id="status">جاري التحليل... قد يستغرق 30 ثانية</div>
        <div id="report"></div>
    </div>
    <script>
        async function process() {
            const file = document.getElementById('fileInput').files[0];
            const tNum = document.getElementById('tNum').value.trim();
            const tName = document.getElementById('tName').value.trim();
            const cDate = document.getElementById('cDate').value;
            if (!file) return alert("يرجى اختيار ملف PDF");
            if (!tNum || !tName || !cDate) return alert("يرجى تعبئة جميع الحقول");
            const fd = new FormData();
            fd.append('file', file);
            fd.append('tNum', tNum);
            fd.append('tName', tName);
            fd.append('bAmount', document.getElementById('bAmount').value);
            fd.append('cDate', cDate);
            document.getElementById('runBtn').disabled = true;
            document.getElementById('status').style.display = 'block';
            document.getElementById('report').style.display = 'none';
            try {
                const r = await fetch('/', { method: 'POST', body: fd });
                const d = await r.json();
                document.getElementById('report').innerHTML = d.report || ('<span style=color:red>خطأ: ' + d.error + '</span>');
                document.getElementById('report').style.display = 'block';
            } catch (e) { alert("خطأ: " + e.message); }
            document.getElementById('status').style.display = 'none';
            document.getElementById('runBtn').disabled = false;
        }
    </script>
</body>
</html>
"""

SYSTEM_PROMPT = """You are a Senior Legal and Compliance Advisor for PetroChina Halfaya FZCO Iraq Branch.
Analyze the uploaded Bid Bond PDF and verify it against the tender requirements.
Output ONLY an HTML table with columns: Criterion | Status | Finding.
Use these exact status values: GREEN, YELLOW, or RED.

Check these 7 criteria:
1. Tender Name and Number - must match exactly (GREEN or RED only, no YELLOW)
2. Beneficiary Name - must be exactly PetroChina Halfaya FZCO Iraq Branch (GREEN or RED only)
3. Currency - must be USD only (GREEN or RED only)
4. Bid Bond Amount - must be equal or greater than required amount (GREEN or RED only)
5. Bank Status - GREEN if CBI approved Iraqi bank, YELLOW if international bank, RED if blacklisted
   Blacklisted banks: United Investment Bank, Al-Watani Islamic Bank, Al Shamal Bank, Babel Bank, Alwarkaa Bank, Islamic Money Bank
6. Validity Duration - GREEN if 240 days or more from closing date, YELLOW if short by 14 days or less, RED if short by more than 14 days
7. Form Compliance - GREEN if matches template, YELLOW if minor deviations, RED if conditional language blocks On First Demand payment

After the table add: Overall Result: PASS or CONDITIONAL or FAIL
Then add: Legal Risk Note: one sentence summary
"""

@app.route("/", methods=["GET", "POST"])
def handle():
    if request.method == "GET":
        return render_template_string(HTML_TEMPLATE)
    f = request.files.get('file')
    if not f:
        return jsonify({"error": "لم يتم رفع أي ملف"}), 400
    try:
        pdf_b64 = base64.b64encode(f.read()).decode('utf-8')
        user_prompt = (
            f"Tender No: {request.form.get('tNum')}\n"
            f"Tender Name: {request.form.get('tName')}\n"
            f"Required Bid Bond Amount: {request.form.get('bAmount')} USD\n"
            f"Bid Closing Date: {request.form.get('cDate')}\n"
            f"Analyze the attached PDF against these requirements."
        )
        response = model.generate_content([
            SYSTEM_PROMPT,
            user_prompt,
            {"mime_type": "application/pdf", "data": pdf_b64}
        ])
        return jsonify({"report": response.text})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
