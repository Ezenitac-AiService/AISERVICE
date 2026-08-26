from flask import Flask, request, jsonify
from flask_cors import CORS
import pymysql
from werkzeug.security import generate_password_hash, check_password_hash
import smtplib
from email.mime.text import MIMEText
import random
import os
from dotenv import load_dotenv
import traceback
import string

load_dotenv()

app = Flask(__name__)
CORS(app)

SMTP_SERVER = os.getenv('SMTP_SERVER')
SMTP_PORT = int(os.getenv('SMTP_PORT', 587))
SMTP_USER = os.getenv('SMTP_USER')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD')

auth_codes_store = {}

def get_db_connection():
    try:
        from db_helper import get_db_connection as helper_conn
        return helper_conn()
    except Exception:
        host = os.getenv('DB_HOST') or os.getenv('host') or 'localhost'
        port = int(os.getenv('DB_PORT', 3306))
        user = os.getenv('DB_USER') or os.getenv('ID') or 'GP'
        password = os.getenv('DB_PASSWORD') or os.getenv('PW') or 'GP123!'
        database = os.getenv('DB_NAME') or os.getenv('DB_NAME3') or os.getenv('DBName') or 'oliview_project'
        return pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )

def safe_format_date(val):
    if not val:
        return None
    if hasattr(val, 'strftime'):
        return val.strftime('%Y-%m-%d')
    return str(val)[:10]

def serialize_val(val):
    if val is None:
        return None
    if hasattr(val, 'strftime'):
        return val.strftime('%Y-%m-%d %H:%M:%S') if hasattr(val, 'hour') else val.strftime('%Y-%m-%d')
    if isinstance(val, (int, float, bool, str)):
        return val
    try:
        import decimal
        if isinstance(val, decimal.Decimal):
            return float(val)
    except Exception:
        pass
    return str(val)

def serialize_row(row):
    if not isinstance(row, dict):
        return row
    return {k: serialize_val(v) for k, v in row.items()}

def serialize_rows(rows):
    if not rows:
        return []
    return [serialize_row(r) for r in rows]

# --- 헬스체크 API ---
@app.route('/api/health', methods=['GET'])
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "ok", "service": "oliview_backend"}), 200

# --- 이메일 중복 체크 API ---
@app.route('/api/check-email', methods=['POST'])
def check_email():
    data = request.json
    email = data.get('email')
    current_brand_id = data.get('currentBrandId')

    if not email:
        return jsonify({"success": False, "message": "이메일을 입력해주세요."}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if current_brand_id:
            cursor.execute("SELECT brand_id FROM brand_managers WHERE email = %s AND brand_id != %s", (email, current_brand_id))
        else:
            cursor.execute("SELECT brand_id FROM brand_managers WHERE email = %s", (email,))
        
        existing = cursor.fetchone()
        if existing:
            return jsonify({"success": True, "isDuplicate": True, "message": "이미 사용 중인 이메일입니다."}), 200
        
        return jsonify({"success": True, "isDuplicate": False}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

import time

@app.route('/api/send-auth-code', methods=['POST'])
def send_auth_code():
    data = request.json or {}
    email = data.get('email')

    if not email:
        return jsonify({"success": False, "message": "이메일을 입력해주세요."}), 400

    now = time.time()
    # Check if there's a recent request within 60s cooldown
    if email in auth_codes_store:
        session = auth_codes_store[email]
        if isinstance(session, dict) and now - session.get('created_at', 0) < 60:
            return jsonify({"success": False, "message": "인증번호가 이미 발송되었습니다. 1분 후 다시 시도해주세요."}), 400

    auth_code = str(random.randint(100000, 999999))
    msg = MIMEText(f"Oliview 브랜드 담당자 가입을 위한 인증번호입니다.\n\n인증번호: [{auth_code}]")
    msg['Subject'] = 'Oliview 회원가입 이메일 인증번호'
    msg['From'] = SMTP_USER
    msg['To'] = email

    try:
        if not SMTP_SERVER or not SMTP_USER or not SMTP_PASSWORD:
            raise ValueError("SMTP 환경 변수가 설정되지 않았습니다.")

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=10)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)
        server.quit()

        auth_codes_store[email] = {
            "code": auth_code,
            "created_at": now,
            "expires_at": now + 300, # 5 min TTL
            "attempts": 0
        }
        return jsonify({"success": True, "message": "인증번호가 발송되었습니다."}), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({
            "success": False, 
            "message": "이메일 발송에 실패했습니다. 메일 주소를 확인하거나 잠시 후 다시 시도해주세요."
        }), 400

@app.route('/api/verify-auth-code', methods=['POST'])
def verify_auth_code():
    data = request.json or {}
    email = data.get('email')
    code = data.get('code')

    if not email or not code:
        return jsonify({"success": False, "message": "이메일과 인증번호를 모두 입력해주세요."}), 400

    session = auth_codes_store.get(email)
    if not session:
        return jsonify({"success": False, "message": "인증번호가 발송되지 않았거나 만료되었습니다."}), 400

    if isinstance(session, dict):
        now = time.time()
        if now > session.get('expires_at', 0):
            del auth_codes_store[email]
            return jsonify({"success": False, "message": "인증번호 유효시간(5분)이 만료되었습니다. 다시 발송해주세요."}), 400
        
        session['attempts'] = session.get('attempts', 0) + 1
        if session['attempts'] > 5:
            del auth_codes_store[email]
            return jsonify({"success": False, "message": "인증 시도 횟수를 초과했습니다 (최대 5회). 다시 발송해주세요."}), 400

        target_code = session.get('code')
    else:
        target_code = session

    if target_code == str(code).strip():
        del auth_codes_store[email]
        return jsonify({"success": True, "message": "인증이 완료되었습니다."}), 200
    else:
        return jsonify({"success": False, "message": "인증번호가 일치하지 않습니다."}), 400

@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    brand_id = data.get('brandId')
    brand_pw = data.get('brandPw')
    managers = data.get('managers')

    if not brand_pw or len(brand_pw) < 8:
        return jsonify({"success": False, "message": "브랜드 비밀번호는 최소 8자 이상이어야 합니다."}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT * FROM brands WHERE brand_id = %s", (brand_id,))
        brand = cursor.fetchone()
        if not brand:
            return jsonify({"success": False, "message": "올리브영에 등록되지 않은 브랜드 고유 번호입니다."}), 400

        cursor.execute("SELECT * FROM brand_accounts WHERE brand_id = %s", (brand_id,))
        existing_account = cursor.fetchone()

        if existing_account:
            if existing_account['status'] in ['ACTIVE', 'WITHDRAWING']:
                return jsonify({"success": False, "message": "이미 가입되었거나 탈퇴 유예 중인 브랜드입니다."}), 400
            elif existing_account['status'] == 'WITHDRAWN':
                brand_pw_hash = generate_password_hash(brand_pw)
                cursor.execute(
                    "UPDATE brand_accounts SET brand_pw_hash = %s, status = 'ACTIVE', withdrawn_at = NULL WHERE brand_id = %s",
                    (brand_pw_hash, brand_id)
                )
                cursor.execute("DELETE FROM brand_managers WHERE brand_id = %s", (brand_id,))
                for manager in managers:
                    if manager.get('name') and manager.get('email') and manager.get('isVerified'):
                        cursor.execute("SELECT manager_id FROM brand_managers WHERE email = %s AND brand_id != %s", (manager['email'], brand_id))
                        if cursor.fetchone():
                            return jsonify({"success": False, "message": f"이미 사용 중인 이메일입니다: {manager['email']}"}), 400

                        manager_pw_hash = generate_password_hash(manager.get('password'))
                        cursor.execute(
                            "INSERT INTO brand_managers (brand_id, name, email, manager_pw_hash) VALUES (%s, %s, %s, %s)",
                            (brand_id, manager['name'], manager['email'], manager_pw_hash)
                        )
                conn.commit()
                return jsonify({"success": True, "message": "재가입이 완료되었습니다."}), 200

        for manager in managers:
            if manager.get('name') and manager.get('email') and manager.get('isVerified'):
                mgr_pw = manager.get('password')
                if not mgr_pw or len(mgr_pw) < 8:
                    return jsonify({"success": False, "message": "담당자 비밀번호는 최소 8자 이상이어야 합니다."}), 400

                cursor.execute("SELECT manager_id FROM brand_managers WHERE email = %s", (manager['email'],))
                if cursor.fetchone():
                    return jsonify({"success": False, "message": f"이미 사용 중인 이메일입니다: {manager['email']}"}), 400

        brand_pw_hash = generate_password_hash(brand_pw)
        cursor.execute("INSERT INTO brand_accounts (brand_id, brand_pw_hash, status) VALUES (%s, %s, 'ACTIVE')", (brand_id, brand_pw_hash))

        for manager in managers:
            if manager.get('name') and manager.get('email') and manager.get('isVerified'): 
                manager_pw_hash = generate_password_hash(manager.get('password'))
                cursor.execute(
                    """
                    INSERT INTO brand_managers 
                    (brand_id, name, email, manager_pw_hash) 
                    VALUES (%s, %s, %s, %s)
                    """,
                    (brand_id, manager['name'], manager['email'], manager_pw_hash)
                )

        conn.commit()
        return jsonify({"success": True, "message": "회원가입이 완료되었습니다."}), 200

    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    brand_id = data.get('brandId')
    email = data.get('email')
    manager_pw = data.get('managerPw')

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            SELECT bm.*, b.brand_name, ba.status, ba.withdrawn_at 
            FROM brand_managers bm
            JOIN brands b ON bm.brand_id = b.brand_id
            JOIN brand_accounts ba ON bm.brand_id = ba.brand_id
            WHERE bm.brand_id = %s AND bm.email = %s
            """, 
            (brand_id, email)
        )
        manager = cursor.fetchone()

        if not manager:
            return jsonify({"success": False, "message": "정보가 일치하지 않습니다."}), 401

        status = manager.get('status', 'ACTIVE')
        withdrawn_at = manager.get('withdrawn_at')

        if status == 'WITHDRAWN':
            return jsonify({"success": False, "message": "탈퇴한 회원입니다. 재가입 시 회원가입을 다시 진행해주세요."}), 400

        if status == 'WITHDRAWING' and withdrawn_at:
            from datetime import datetime, timedelta
            if datetime.now() - withdrawn_at > timedelta(days=30):
                cursor.execute("UPDATE brand_accounts SET status = 'WITHDRAWN' WHERE brand_id = %s", (brand_id,))
                conn.commit()
                return jsonify({"success": False, "message": "탈퇴 유예 기간(30일)이 만료되어 완전 탈퇴 처리되었습니다. 재가입해주세요."}), 400
            else:
                return jsonify({
                    "success": False, 
                    "isWithdrawing": True,
                    "message": "탈퇴 유예 계정입니다. 탈퇴를 취소하고 로그인하시겠습니까?"
                }), 200

        if check_password_hash(manager['manager_pw_hash'], manager_pw):
            return jsonify({
                "success": True, 
                "message": "로그인 성공!", 
                "brandId": manager['brand_id'],
                "brandName": manager['brand_name'],
                "managerName": manager['name']
            }), 200
        else:
            return jsonify({"success": False, "message": "정보가 일치하지 않습니다."}), 401

    finally:
        cursor.close()
        conn.close()

@app.route('/api/cancel-withdrawal', methods=['POST'])
def cancel_withdrawal():
    data = request.json
    brand_id = data.get('brandId')
    email = data.get('email')
    manager_pw = data.get('managerPw')

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT bm.* FROM brand_managers bm
            WHERE bm.brand_id = %s AND bm.email = %s
            """, (brand_id, email)
        )
        manager = cursor.fetchone()
        if not manager or not check_password_hash(manager['manager_pw_hash'], manager_pw):
            return jsonify({"success": False, "message": "비밀번호가 일치하지 않습니다."}), 400

        cursor.execute(
            "UPDATE brand_accounts SET status = 'ACTIVE', withdrawn_at = NULL WHERE brand_id = %s",
            (brand_id,)
        )
        conn.commit()
        return jsonify({"success": True, "message": "탈퇴가 성공적으로 취소되었습니다. 다시 로그인해주세요."}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/brand-info/withdraw', methods=['POST'])
def withdraw_brand():
    data = request.json
    brand_id = data.get('brandId')
    current_brand_pw = data.get('currentBrandPw')

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT brand_pw_hash FROM brand_accounts WHERE brand_id = %s", (brand_id,))
        account = cursor.fetchone()
        if not account or not check_password_hash(account['brand_pw_hash'], current_brand_pw):
            return jsonify({"success": False, "message": "브랜드 비밀번호가 일치하지 않습니다."}), 400

        cursor.execute(
            "UPDATE brand_accounts SET status = 'WITHDRAWING', withdrawn_at = NOW() WHERE brand_id = %s",
            (brand_id,)
        )
        conn.commit()
        return jsonify({"success": True, "message": "회원탈퇴가 신청되었습니다. 30일 이내에 로그인하시면 탈퇴가 취소됩니다."}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/brands/<int:brand_id>/products', methods=['GET'])
def get_products(brand_id):
    category_id = request.args.get('categoryId')
    conn = None
    cursor = None
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        if not category_id or category_id == 'all':
            sql = """
                SELECT p.*, b.brand_name, GROUP_CONCAT(DISTINCT pc.category_id) AS category_ids 
                FROM products p
                JOIN brands b ON p.brand_id = b.brand_id
                LEFT JOIN product_categories pc ON p.product_id = pc.product_id
                WHERE p.brand_id = %s
                GROUP BY p.product_id
            """
            cursor.execute(sql, (brand_id,))
        else:
            target_category_ids = [str(category_id)]
            queue = [str(category_id)]
            
            while queue:
                current_id = queue.pop(0)
                cursor.execute("SELECT category_id FROM categories WHERE parent_category_id = %s", (current_id,))
                sub_categories = cursor.fetchall()
                
                for sub in sub_categories:
                    sub_id = str(sub['category_id'] if isinstance(sub, dict) else sub[0])
                    if sub_id not in target_category_ids:
                        target_category_ids.append(sub_id)
                        queue.append(sub_id)
            
            format_strings = ','.join(['%s'] * len(target_category_ids))
            
            sql = f"""
                SELECT p.*, b.brand_name, GROUP_CONCAT(DISTINCT pc2.category_id) AS category_ids 
                FROM products p
                JOIN brands b ON p.brand_id = b.brand_id
                JOIN product_categories pc ON p.product_id = pc.product_id
                LEFT JOIN product_categories pc2 ON p.product_id = pc2.product_id
                WHERE p.brand_id = %s AND pc.category_id IN ({format_strings})
                GROUP BY p.product_id
            """
            cursor.execute(sql, [brand_id] + target_category_ids)
            
        products = cursor.fetchall()
        return jsonify({"success": True, "products": serialize_rows(products), "fallback": False}), 200
        
    except Exception as e:
        traceback.print_exc()
        # Graceful Fallback: 프론트엔드 크래시 방지용 안전한 빈 배열 응답 반환
        return jsonify({
            "success": True,
            "products": [],
            "fallback": True,
            "message": "해당 브랜드의 상품 정보가 준비 중이거나 일시적으로 조회할 수 없습니다."
        }), 200
    finally:
        if cursor:
            try: cursor.close()
            except: pass
        if conn:
            try: conn.close()
            except: pass

@app.route('/api/brands/<int:brand_id>/categories', methods=['GET'])
def get_brand_categories(brand_id):
    conn = None
    cursor = None
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM categories")
        categories = cursor.fetchall()
        return jsonify({"success": True, "categories": serialize_rows(categories), "fallback": False}), 200
        
    except Exception as e:
        traceback.print_exc()
        # Graceful Fallback: 프론트엔드 크래시 방지용 안전한 빈 카테고리 응답 반환
        return jsonify({
            "success": True,
            "categories": [],
            "fallback": True,
            "message": "카테고리 정보가 준비 중입니다."
        }), 200
    finally:
        if cursor:
            try: cursor.close()
            except: pass
        if conn:
            try: conn.close()
            except: pass

@app.route('/api/products/<int:product_id>', methods=['GET'])
def get_product_detail(product_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        sql_product = """
            SELECT p.*, b.brand_name 
            FROM products p
            LEFT JOIN brands b ON p.brand_id = b.brand_id
            WHERE p.product_id = %s
        """
        cursor.execute(sql_product, (product_id,))
        product = cursor.fetchone()
        
        if not product:
            return jsonify({"success": False, "message": "상품을 찾을 수 없습니다."}), 404

        cursor.execute("SELECT * FROM product_options WHERE product_id = %s", (product_id,))
        options = cursor.fetchall()

        sql_reviews = """
            SELECT r.*, po.option_name 
            FROM reviews r
            LEFT JOIN product_options po ON r.product_option_id = po.product_option_id
            WHERE r.product_id = %s
            ORDER BY r.review_date DESC
        """
        cursor.execute(sql_reviews, (product_id,))
        reviews = cursor.fetchall()

        return jsonify({
            "success": True,
            "product": serialize_row(product),
            "options": serialize_rows(options),
            "reviews": serialize_rows(reviews[:100] if reviews else [])
        }), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/products/<int:product_id>/analysis-report', methods=['GET'])
def get_product_analysis_report(product_id):
    selected_attribute_name = request.args.get('attribute_name', type=str)
    sub_tab = request.args.get('tab', default='maintain', type=str)

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        sql_latest_report = """
            SELECT llm_product_report_id, keep_summary, improvement_summary, overall_summary 
            FROM llm_product_reports 
            WHERE product_id = %s 
            ORDER BY generated_at DESC 
            LIMIT 1
        """
        cursor.execute(sql_latest_report, (product_id,))
        latest_report = cursor.fetchone()

        report_id = latest_report['llm_product_report_id'] if latest_report else None

        sql_radar = """
            SELECT 
                pass.analysis_category_id AS attribute_id,
                pass.attribute_name,
                pass.total_sentence_count AS total_count,
                pass.positive_sentence_count AS pos_count,
                pass.negative_sentence_count AS neg_count,
                pass.neutral_sentence_count AS neu_count,
                pass.positive_ratio AS score,
                lpar.positive_summary,
                lpar.negative_summary
            FROM product_attribute_sentiment_stats pass
            LEFT JOIN llm_product_attribute_reports lpar 
                   ON lpar.llm_product_report_id = %s
                  AND pass.analysis_category_id = lpar.analysis_category_id
                  AND pass.attribute_name = lpar.display_name
            WHERE pass.product_id = %s
            ORDER BY pass.analysis_category_id ASC
        """
        cursor.execute(sql_radar, (report_id, product_id))
        attribute_reports = cursor.fetchall()

        radar_data = []
        seen_attributes = set()
        for report in attribute_reports:
            attr_name = report.get('attribute_name')
            if attr_name and attr_name not in seen_attributes:
                seen_attributes.add(attr_name)
                radar_data.append({
                    "attribute_id": report.get('attribute_id'),
                    "attribute_name": attr_name,
                    "total_count": report.get('total_count') or 0,
                    "pos_count": report.get('pos_count') or 0,
                    "neg_count": report.get('neg_count') or 0,
                    "neu_count": report.get('neu_count') or 0,
                    "score": float(report.get('score') or 0),
                    "positive_summary": report.get('positive_summary') or "해당 속성에 대한 강점 분석 요약이 없습니다.",
                    "negative_summary": report.get('negative_summary') or "해당 속성에 대한 개선점 분석 요약이 없습니다."
                })

        sql_overall_stats = """
            SELECT * FROM product_overall_sentiment_stats WHERE product_id = %s
        """
        cursor.execute(sql_overall_stats, (product_id,))
        raw_overall = cursor.fetchone()
        overall_stats = serialize_row(raw_overall) if raw_overall else {
            "total_sentence_count": 0,
            "positive_count": 0,
            "negative_count": 0,
            "neutral_count": 0,
            "positive_ratio": 0.0,
            "negative_ratio": 0.0
        }

        overall_report_data = {
            "keep_summary": latest_report.get('keep_summary') if latest_report else "등록된 긍정(Keep) 종합 요약이 없습니다.",
            "improvement_summary": latest_report.get('improvement_summary') if latest_report else "등록된 부정(Improvement) 종합 요약이 없습니다.",
            "overall_summary": latest_report.get('overall_summary') if latest_report else "등록된 전체(Overall) 종합 요약이 없습니다."
        }

        reviews_data = []
        sentiment_filter = request.args.get('sentiment', type=str)
        
        if selected_attribute_name:
            if sub_tab == 'maintain':
                sentiment_condition = "LOWER(TRIM(asr.sentiment_label)) IN ('positive', '긍정', '1', 'pos', 'p', 'true')"
            elif sub_tab == 'improve':
                sentiment_condition = "LOWER(TRIM(asr.sentiment_label)) IN ('negative', '부정', '0', 'neg', 'n', 'false')"
            elif sub_tab == 'neutral':
                sentiment_condition = "(LOWER(TRIM(asr.sentiment_label)) IN ('neutral', '중립', 'neu', '2') OR asr.sentiment_label IS NULL)"
            else:
                sentiment_condition = "1=1"

            sql_reviews = f"""
                SELECT 
                    r.review_id,
                    r.review_score AS rating,
                    r.review_date,
                    r.review_content AS full_review_text,
                    ras.sequence_no,
                    ras.separated_sentence AS sentiment_sentence,
                    asr.sentiment_label,
                    po.option_name,
                    aca.display_name AS attribute_name
                FROM reviews r
                JOIN review_aspect_sentences ras ON r.review_id = ras.review_id
                JOIN product_categories pc ON r.product_id = pc.product_id
                JOIN categories c ON c.category_id = pc.category_id
                LEFT JOIN categories parent ON c.parent_category_id = parent.category_id
                LEFT JOIN categories grandparent ON parent.parent_category_id = grandparent.category_id
                JOIN analysis_category_attributes aca 
                  ON aca.analysis_category_id = COALESCE(
                        (SELECT ac.analysis_category_id FROM analysis_category_attributes ac WHERE ac.analysis_category_id = c.category_id AND ac.display_name = %s LIMIT 1),
                        (SELECT ac.analysis_category_id FROM analysis_category_attributes ac WHERE ac.analysis_category_id = parent.category_id AND ac.display_name = %s LIMIT 1),
                        (SELECT ac.analysis_category_id FROM analysis_category_attributes ac WHERE ac.analysis_category_id = grandparent.category_id AND ac.display_name = %s LIMIT 1),
                        ras.analysis_category_id
                     )
                 AND ras.model_attribute_name = aca.model_attribute_name
                 AND aca.display_name = %s
                LEFT JOIN aspect_sentiment_results asr ON ras.aspect_sentence_id = asr.aspect_sentence_id
                LEFT JOIN product_options po ON r.product_option_id = po.product_option_id
                WHERE r.product_id = %s 
                  AND {sentiment_condition}
                ORDER BY r.review_date DESC, ras.sequence_no ASC
            """
            cursor.execute(sql_reviews, (selected_attribute_name, selected_attribute_name, selected_attribute_name, selected_attribute_name, product_id))
            
        elif sentiment_filter:
            if sentiment_filter == 'positive':
                sent_cond = "LOWER(TRIM(asr.sentiment_label)) IN ('positive', '긍정', '1', 'pos', 'p', 'true')"
            elif sentiment_filter == 'negative':
                sent_cond = "LOWER(TRIM(asr.sentiment_label)) IN ('negative', '부정', '0', 'neg', 'n', 'false')"
            elif sentiment_filter == 'neutral':
                sent_cond = "(LOWER(TRIM(asr.sentiment_label)) IN ('neutral', '중립', 'neu', '2') OR asr.sentiment_label IS NULL)"
            else:
                sent_cond = "1=1"

            sql_overall_reviews = f"""
                SELECT 
                    r.review_id,
                    r.review_score AS rating,
                    r.review_date,
                    r.review_content AS full_review_text,
                    ras.sequence_no,
                    ras.separated_sentence AS sentiment_sentence,
                    asr.sentiment_label,
                    po.option_name,
                    aca.display_name AS attribute_name
                FROM reviews r
                JOIN review_aspect_sentences ras ON r.review_id = ras.review_id
                LEFT JOIN aspect_sentiment_results asr ON ras.aspect_sentence_id = asr.aspect_sentence_id
                LEFT JOIN product_options po ON r.product_option_id = po.product_option_id
                LEFT JOIN analysis_category_attributes aca 
                  ON ras.analysis_category_id = aca.analysis_category_id 
                 AND ras.model_attribute_name = aca.model_attribute_name
                WHERE r.product_id = %s 
                  AND {sent_cond}
                ORDER BY r.review_date DESC, ras.sequence_no ASC
            """
            cursor.execute(sql_overall_reviews, (product_id,))

        matched_rows = cursor.fetchall()
        for row in matched_rows:
            raw_label = str(row.get('sentiment_label') or '').strip().lower()
            if raw_label in ('positive', '긍정', '1', 'pos', 'p', 'true'):
                norm_label = 'positive'
            elif raw_label in ('negative', '부정', '0', 'neg', 'n', 'false'):
                norm_label = 'negative'
            else:
                norm_label = 'neutral'

            reviews_data.append({
                "review_id": row.get('review_id'),
                "sequence_no": row.get('sequence_no'),
                "sentiment_sentence": row.get('sentiment_sentence'),
                "sentiment_label": norm_label,
                "rating": row.get('rating') or 5,
                "review_created_at": safe_format_date(row.get('review_date')),
                "option_name": row.get('option_name') or "기본 옵션",
                "full_review_text": row.get('full_review_text'),
                "attribute_name": row.get('attribute_name')
            })

        return jsonify({
            "success": True,
            "radar_data": radar_data,
            "overall_stats": overall_stats,
            "overall_report": overall_report_data,
            "reviews_data": reviews_data
        }), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/brand-info/<brand_id>', methods=['GET'])
def get_brand_info(brand_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT brand_id FROM brand_accounts WHERE brand_id = %s", (brand_id,))
        brand = cursor.fetchone()
        if not brand:
            return jsonify({"success": False, "message": "존재하지 않는 브랜드입니다."}), 404

        cursor.execute("SELECT manager_id, name, email, is_active FROM brand_managers WHERE brand_id = %s", (brand_id,))
        managers = cursor.fetchall()

        return jsonify({"success": True, "brand_id": brand['brand_id'], "managers": managers}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/brand-info/update', methods=['PUT'])
def update_brand_info():
    data = request.json
    brand_id = data.get('brandId')
    current_brand_pw = data.get('currentBrandPw')
    new_brand_pw = data.get('newBrandPw')
    managers_data = data.get('managers', [])

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT brand_pw_hash FROM brand_accounts WHERE brand_id = %s", (brand_id,))
        account = cursor.fetchone()
        if not account or not check_password_hash(account['brand_pw_hash'], current_brand_pw):
            return jsonify({"success": False, "message": "기존 브랜드 비밀번호가 일치하지 않습니다."}), 400

        if new_brand_pw:
            if len(new_brand_pw) < 8:
                return jsonify({"success": False, "message": "새 브랜드 비밀번호는 최소 8자 이상이어야 합니다."}), 400
            new_pw_hash = generate_password_hash(new_brand_pw)
            cursor.execute("UPDATE brand_accounts SET brand_pw_hash = %s WHERE brand_id = %s", (new_pw_hash, brand_id))

        cursor.execute("SELECT manager_id FROM brand_managers WHERE brand_id = %s", (brand_id,))
        existing_managers = cursor.fetchall()
        existing_ids = [m['manager_id'] for m in existing_managers]

        submitted_ids = [m.get('manager_id') for m in managers_data if m.get('manager_id')]

        for db_id in existing_ids:
            if db_id not in submitted_ids:
                if len(existing_ids) - len([i for i in existing_ids if i not in submitted_ids]) < 1:
                    return jsonify({"success": False, "message": "최소 1명의 담당자는 유지되어야 합니다."}), 400
                cursor.execute("DELETE FROM brand_managers WHERE manager_id = %s", (db_id,))

        for m in managers_data:
            manager_id = m.get('manager_id')
            name = m.get('name')
            email = m.get('email')
            manager_pw = m.get('managerPw')
            is_active = m.get('is_active', True)

            if not name or not email:
                return jsonify({"success": False, "message": "담당자 이름과 이메일은 필수입니다."}), 400

            if manager_id:
                cursor.execute("SELECT manager_id FROM brand_managers WHERE email = %s AND manager_id != %s", (email, manager_id))
            else:
                cursor.execute("SELECT manager_id FROM brand_managers WHERE email = %s", (email,))

            if cursor.fetchone():
                return jsonify({"success": False, "message": f"이미 다른 계정에서 사용 중인 이메일입니다: {email}"}), 400

            if manager_id:
                if manager_pw:
                    if len(manager_pw) < 8:
                        return jsonify({"success": False, "message": "담당자 비밀번호는 최소 8자 이상이어야 합니다."}), 400
                    pw_hash = generate_password_hash(manager_pw)
                    cursor.execute(
                        "UPDATE brand_managers SET name = %s, email = %s, manager_pw_hash = %s, is_active = %s WHERE manager_id = %s",
                        (name, email, pw_hash, is_active, manager_id)
                    )
                else:
                    cursor.execute(
                        "UPDATE brand_managers SET name = %s, email = %s, is_active = %s WHERE manager_id = %s",
                        (name, email, is_active, manager_id)
                    )
            else:
                if not manager_pw or len(manager_pw) < 8:
                    return jsonify({"success": False, "message": "새 담당자 비밀번호는 최소 8자 이상이어야 합니다."}), 400
                pw_hash = generate_password_hash(manager_pw)
                cursor.execute(
                    "INSERT INTO brand_managers (brand_id, name, email, manager_pw_hash, is_active) VALUES (%s, %s, %s, %s, %s)",
                    (brand_id, name, email, pw_hash, True)
                )

        conn.commit()
        return jsonify({"success": True, "message": "회원정보가 성공적으로 수정되었습니다."}), 200

    except Exception as e:
        conn.rollback()
        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/check-manager-pw', methods=['POST'])
def check_manager_pw():
    data = request.json
    manager_id = data.get('manager_id')
    new_pw = data.get('new_pw')

    if not manager_id or not new_pw:
        return jsonify({"success": False, "message": "필수 정보가 누락되었습니다."}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT manager_pw_hash FROM brand_managers WHERE manager_id = %s", (manager_id,))
        manager = cursor.fetchone()

        if not manager:
            return jsonify({"success": False, "message": "존재하지 않는 담당자입니다."}), 404

        is_duplicate = check_password_hash(manager['manager_pw_hash'], new_pw)
        return jsonify({"success": True, "isDuplicate": is_duplicate}), 200

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/subscribe', methods=['POST'])
def process_subscription():
    data = request.json
    brand_id = data.get('brandId')
    plan_id = data.get('planId')
    client_amount = data.get('amount')
    payment_method = data.get('paymentMethod', 'kakaopay')
    provider_name = data.get('providerName', '알 수 없음') 
    card_number = data.get('cardNumber', '') 

    valid_prices = {1: 100000, 2: 300000, 3: 500000, 4: 700000, 5: 1000000}

    try:
        plan_key = int(plan_id)
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "유효하지 않은 플랜 번호입니다."}), 400

    expected_amount = valid_prices.get(plan_key)
    if expected_amount is None:
        return jsonify({"success": False, "message": "존재하지 않는 구독 플랜입니다."}), 400

    if client_amount != 100 and client_amount != expected_amount:
        return jsonify({"success": False, "message": "결제 금액이 위변조되었습니다."}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT account_id FROM brand_accounts WHERE brand_id = %s", (brand_id,))
        account = cursor.fetchone()
        if not account:
            return jsonify({"success": False, "message": "계정 정보를 찾을 수 없습니다."}), 404
        account_id = account['account_id']

        cursor.execute("SELECT method_id FROM payment_methods WHERE account_id = %s AND method_type = %s AND provider_name = %s AND card_number = %s", (account_id, payment_method, provider_name, card_number))
        existing_method = cursor.fetchone()

        if not existing_method:
            cursor.execute("INSERT INTO payment_methods (account_id, method_type, provider_name, card_number, created_at) VALUES (%s, %s, %s, %s, NOW())", (account_id, payment_method, provider_name, card_number))

        cursor.execute("INSERT INTO payment_history (account_id, plan_id, amount, payment_method, paid_at) VALUES (%s, %s, %s, %s, NOW())", (account_id, plan_id, client_amount, payment_method))

        cursor.execute("SELECT subscription_id FROM brand_subscriptions WHERE account_id = %s", (account_id,))
        subscription = cursor.fetchone()

        if subscription:
            cursor.execute("UPDATE brand_subscriptions SET plan_id = %s, status = 'ACTIVE', next_billing_date = DATE_ADD(NOW(), INTERVAL 1 MONTH), updated_at = NOW() WHERE account_id = %s", (plan_id, account_id))
        else:
            cursor.execute("INSERT INTO brand_subscriptions (account_id, plan_id, status, next_billing_date, updated_at) VALUES (%s, %s, 'ACTIVE', DATE_ADD(NOW(), INTERVAL 1 MONTH), NOW())", (account_id, plan_id))

        conn.commit()
        return jsonify({"success": True, "message": "결제 수단 및 구독 결제가 완료되었습니다."}), 200

    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/subscription/<brand_id>', methods=['GET'])
def get_subscription_info(brand_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT account_id FROM brand_accounts WHERE brand_id = %s", (brand_id,))
        account = cursor.fetchone()
        if not account:
            return jsonify({"success": False, "message": "계정 정보를 찾을 수 없습니다."}), 404
        account_id = account['account_id']

        cursor.execute("""
            SELECT p.plan_name, ph.amount, ph.paid_at, bs.next_billing_date, bs.cancel_reserved, bs.status 
            FROM brand_subscriptions bs
            LEFT JOIN subscription_plans p ON bs.plan_id = p.plan_id
            LEFT JOIN payment_history ph ON ph.account_id = bs.account_id
            WHERE bs.account_id = %s 
            ORDER BY ph.paid_at DESC LIMIT 1
        """, (account_id,))
        sub = cursor.fetchone()

        cursor.execute("""
            SELECT provider_name, card_number, method_type
            FROM payment_methods 
            WHERE account_id = %s 
            ORDER BY created_at DESC LIMIT 1
        """, (account_id,))
        payment_method = cursor.fetchone()

        cursor.execute("""
            SELECT ph.payment_id AS history_id, 
                   ph.amount, 
                   ph.payment_method, 
                   ph.paid_at, 
                   ph.status,
                   ph.refunded_at,
                   sp.plan_name
            FROM payment_history ph
            JOIN subscription_plans sp ON ph.plan_id = sp.plan_id
            WHERE ph.account_id = %s
            ORDER BY ph.paid_at DESC
        """, (account_id,))
        history_raw = cursor.fetchall()

        history = []
        for item in history_raw:
            history.append({
                "history_id": item['history_id'],
                "amount": item['amount'],
                "payment_method": item['payment_method'],
                "paid_at": safe_format_date(item['paid_at']),
                "plan_name": item['plan_name'],
                "status": item.get('status') or 'PAID',
                "refunded_at": safe_format_date(item.get('refunded_at'))
            })

        subscription_data = {
            "isSubscribed": True if sub and sub.get('status') == 'ACTIVE' else False,
            "status": sub.get('status') if sub else "NONE",
            "planName": sub.get('plan_name') if sub else None,
            "price": sub.get('amount') if sub else 0,
            "paidAt": safe_format_date(sub.get('paid_at')) if sub else None,
            "nextBillingDate": safe_format_date(sub.get('next_billing_date')) if sub else None,
            "cancelReserved": bool(sub.get('cancel_reserved', 0)) if sub else False
        }

        return jsonify({
            "success": True,
            "subscription": subscription_data,
            "payment_method": payment_method,
            "history": history
        }), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

# 환불 신청 API (서비스 이용 내역 검증 및 sub_category_id 컬럼 반영)
@app.route('/api/subscription/refund', methods=['POST'])
def refund_subscription():
    data = request.json
    payment_id = data.get('paymentId')
    brand_id = data.get('brandId')

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # 1. 결제 정보 및 7일 이내 여부 조회
        cursor.execute("""
            SELECT ph.*, TIMESTAMPDIFF(DAY, ph.paid_at, NOW()) AS days_passed, ba.account_id
            FROM payment_history ph
            JOIN brand_accounts ba ON ph.account_id = ba.account_id
            WHERE ph.payment_id = %s AND ba.brand_id = %s
        """, (payment_id, brand_id))
        payment = cursor.fetchone()

        if not payment:
            return jsonify({"success": False, "message": "결제 내역을 찾을 수 없습니다."}), 404

        if payment.get('status') == 'REFUNDED':
            return jsonify({"success": False, "message": "이미 환불 처리된 결제건입니다."}), 400

        if payment.get('days_passed', 99) > 7:
            return jsonify({"success": False, "message": "결제 후 7일이 경과하여 환불이 불가능합니다."}), 400

        # 2. 서비스 이용 여부 다중 검증
        # (가) 경쟁사 제품 상세/조회 내역 존재 여부
        cursor.execute("""
            SELECT view_id FROM competitor_product_views 
            WHERE account_id = %s
        """, (payment['account_id'],))
        views_usage = cursor.fetchone()

        # (나) 타사 브랜드 카테고리 구독/선택 설정 여부 (컬럼명 sub_category_id)
        cursor.execute("""
            SELECT sub_category_id FROM brand_subscription_categories 
            WHERE account_id = %s AND selected_categories IS NOT NULL AND selected_categories != '[]'
        """, (payment['account_id'],))
        category_usage = cursor.fetchone()

        if views_usage or category_usage:
            return jsonify({
                "success": False, 
                "message": "구독 플랜 결제 후 타사 분석/조회 서비스를 이미 이용하셨으므로 환불 신청이 불가능합니다."
            }), 400

        # 3. 환불 상태 처리
        cursor.execute("""
            UPDATE payment_history 
            SET status = 'REFUNDED', refunded_at = NOW() 
            WHERE payment_id = %s
        """, (payment_id,))

        cursor.execute("""
            UPDATE brand_subscriptions 
            SET status = 'NONE', updated_at = NOW() 
            WHERE account_id = %s
        """, (payment['account_id'],))

        conn.commit()
        return jsonify({"success": True, "message": "환불 처리가 성공적으로 완료되었습니다."}), 200

    except Exception as e:
        conn.rollback()
        traceback.print_exc()
        return jsonify({
            "success": False, 
            "message": "환불 처리 중 일시적인 시스템 오류가 발생했습니다. 잠시 후 다시 시도해 주시기 바랍니다."
        }), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/brands', methods=['GET'])
def get_all_brands():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT brand_id, brand_name, brand_code FROM brands WHERE is_active = 1")
        brands = cursor.fetchall()
        return jsonify({"success": True, "brands": brands}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/user/status', methods=['POST'])
def get_user_status():
    data = request.json
    brand_id = data.get('brandId')
    if not brand_id:
        return jsonify({"success": False, "message": "브랜드 ID가 없습니다."}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT brand_id FROM brand_managers WHERE brand_id = %s LIMIT 1", (brand_id,))
        manager = cursor.fetchone()
        if not manager:
            return jsonify({"success": True, "isLoggedIn": False}), 200

        cursor.execute("SELECT account_id FROM brand_accounts WHERE brand_id = %s LIMIT 1", (brand_id,))
        account = cursor.fetchone()
        account_id = account['account_id'] if account else None

        cursor.execute("""
            SELECT bs.plan_id, bs.status, p.plan_name, bs.next_billing_date 
            FROM brand_subscriptions bs
            LEFT JOIN subscription_plans p ON bs.plan_id = p.plan_id
            WHERE bs.account_id = %s AND bs.status = 'ACTIVE'
        """, (account_id,))
        subscription = cursor.fetchone()

        if not subscription:
            return jsonify({"success": True, "isLoggedIn": True, "brandId": brand_id, "subscription": {"isSubscribed": False, "status": "NONE"}}), 200

        return jsonify({
            "success": True,
            "isLoggedIn": True,
            "brandId": brand_id,
            "subscription": {
                "isSubscribed": True,
                "status": subscription.get('status'),
                "planName": subscription.get('plan_name'),
                "nextBillingDate": safe_format_date(subscription.get('next_billing_date'))
            }
        }), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/products/<int:product_id>/reviews-detail', methods=['GET'])
def get_product_reviews_detail(product_id):
    sort = request.args.get('sort', default='all', type=str)
    attribute_filter = request.args.get('attribute_name', default='all', type=str)

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        order_clause = "ORDER BY r.review_date DESC"
        if sort == 'high':
            order_clause = "ORDER BY r.review_score DESC, r.review_date DESC"
        elif sort == 'low':
            order_clause = "ORDER BY r.review_score ASC, r.review_date DESC"

        if attribute_filter != 'all':
            sql_reviews = f"""
                SELECT DISTINCT
                    r.review_id,
                    r.review_score AS rating,
                    r.review_date,
                    r.review_content,
                    po.option_name
                FROM reviews r
                LEFT JOIN product_options po ON r.product_option_id = po.product_option_id
                JOIN review_aspect_sentences ras ON r.review_id = ras.review_id
                LEFT JOIN analysis_category_attributes aca 
                  ON ras.analysis_category_id = aca.analysis_category_id 
                 AND ras.model_attribute_name = aca.model_attribute_name
                WHERE r.product_id = %s AND aca.display_name = %s
                {order_clause}
            """
            cursor.execute(sql_reviews, (product_id, attribute_filter))
        else:
            sql_reviews = f"""
                SELECT 
                    r.review_id,
                    r.review_score AS rating,
                    r.review_date,
                    r.review_content,
                    po.option_name
                FROM reviews r
                LEFT JOIN product_options po ON r.product_option_id = po.product_option_id
                WHERE r.product_id = %s
                {order_clause}
            """
            cursor.execute(sql_reviews, (product_id,))
        
        reviews_raw = cursor.fetchall()
        review_ids = [r['review_id'] for r in reviews_raw]

        if not review_ids:
            return jsonify({"success": True, "reviews": []}), 200

        format_strings = ','.join(['%s'] * len(review_ids))
        sql_sentences = f"""
            SELECT 
                ras.review_id,
                ras.aspect_sentence_id,
                ras.sequence_no,
                ras.separated_sentence,
                asr.sentiment_label,
                aca.display_name AS attribute_name
            FROM review_aspect_sentences ras
            LEFT JOIN aspect_sentiment_results asr ON ras.aspect_sentence_id = asr.aspect_sentence_id
            LEFT JOIN analysis_category_attributes aca 
              ON ras.analysis_category_id = aca.analysis_category_id 
             AND ras.model_attribute_name = aca.model_attribute_name
            WHERE ras.review_id IN ({format_strings})
            ORDER BY ras.review_id, ras.sequence_no ASC
        """
        cursor.execute(sql_sentences, tuple(review_ids))
        sentences_raw = cursor.fetchall()

        sentences_by_review = {}
        for s in sentences_raw:
            r_id = s['review_id']
            if r_id not in sentences_by_review:
                sentences_by_review[r_id] = []
            
            raw_label = str(s['sentiment_label'] or '').strip().lower()
            if raw_label in ('positive', '긍정', '1', 'pos', 'p', 'true'):
                norm_label = 'positive'
            elif raw_label in ('negative', '부정', '0', 'neg', 'n', 'false'):
                norm_label = 'negative'
            else:
                norm_label = 'neutral'

            if not any(item['aspect_sentence_id'] == s['aspect_sentence_id'] for item in sentences_by_review[r_id]):
                sentences_by_review[r_id].append({
                    "aspect_sentence_id": s['aspect_sentence_id'],
                    "sequence_no": s['sequence_no'],
                    "separated_sentence": s['separated_sentence'],
                    "sentiment_label": norm_label,
                    "attribute_name": s['attribute_name']
                })

        result_reviews = []
        for rev in reviews_raw:
            r_id = rev['review_id']
            rev_sentences = sentences_by_review.get(r_id, [])

            pos_count = sum(1 for s in rev_sentences if s['sentiment_label'] == 'positive')
            neg_count = sum(1 for s in rev_sentences if s['sentiment_label'] == 'negative')
            neu_count = sum(1 for s in rev_sentences if s['sentiment_label'] == 'neutral')

            result_reviews.append({
                "review_id": r_id,
                "rating": rev['rating'] or 5,
                "review_date": safe_format_date(rev['review_date']),
                "review_content": rev['review_content'] or '',
                "option_name": rev['option_name'] or '기본 옵션',
                "sentences": rev_sentences,
                "counts": {
                    "positive": pos_count,
                    "negative": neg_count,
                    "neutral": neu_count
                }
            })

        return jsonify({
            "success": True,
            "reviews": result_reviews
        }), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/competitor/views/<int:brand_id>', methods=['GET'])
def get_competitor_views(brand_id):
    cycle_key = request.args.get('cycleKey')
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT account_id FROM brand_accounts WHERE brand_id = %s", (brand_id,))
        account = cursor.fetchone()
        if not account:
            return jsonify({"success": False, "message": "계정 정보를 찾을 수 없습니다."}), 404
        account_id = account['account_id']

        cursor.execute("""
            SELECT product_id AS id, product_name AS name, brand_name AS brandName, 
                   product_image_url AS imageUrl, is_free_benefit AS isFreeBenefit 
            FROM competitor_product_views 
            WHERE account_id = %s AND cycle_key = %s
        """, (account_id, cycle_key))
        views = cursor.fetchall()
        return jsonify({"success": True, "views": views}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/competitor/views', methods=['POST'])
def add_competitor_view():
    data = request.json
    brand_id = data.get('brandId')
    cycle_key = data.get('cycleKey')
    item = data.get('item')

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT account_id FROM brand_accounts WHERE brand_id = %s", (brand_id,))
        account = cursor.fetchone()
        if not account:
            return jsonify({"success": False, "message": "계정 정보를 찾을 수 없습니다."}), 404
        account_id = account['account_id']

        cursor.execute("""
            SELECT view_id FROM competitor_product_views 
            WHERE account_id = %s AND cycle_key = %s AND product_id = %s
        """, (account_id, cycle_key, item['id']))
        
        if not cursor.fetchone():
            cursor.execute("""
                INSERT INTO competitor_product_views 
                (account_id, cycle_key, product_id, product_name, brand_name, product_image_url, is_free_benefit) 
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                account_id, cycle_key, item['id'], item['name'], 
                item['brandName'], item['imageUrl'], item.get('isFreeBenefit', False)
            ))
            conn.commit()

        return jsonify({"success": True}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/competitor/categories/<int:brand_id>', methods=['GET'])
def get_competitor_categories(brand_id):
    cycle_key = request.args.get('cycleKey')
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT account_id FROM brand_accounts WHERE brand_id = %s", (brand_id,))
        account = cursor.fetchone()
        if not account:
            return jsonify({"success": False, "message": "계정 정보를 찾을 수 없습니다."}), 404
        account_id = account['account_id']

        cursor.execute("""
            SELECT selected_categories, change_count 
            FROM brand_subscription_categories 
            WHERE account_id = %s AND cycle_key = %s
        """, (account_id, cycle_key))
        row = cursor.fetchone()
        
        if not row:
            return jsonify({"success": True, "selectedCategories": [], "changeCount": 0}), 200

        import json
        categories = json.loads(row['selected_categories']) if row['selected_categories'] else []
        return jsonify({"success": True, "selectedCategories": categories, "changeCount": row['change_count']}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/competitor/categories', methods=['POST'])
def save_competitor_categories():
    data = request.json
    brand_id = data.get('brandId')
    cycle_key = data.get('cycleKey')
    selected_categories = data.get('selectedCategories', [])
    change_count = data.get('changeCount', 0)

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT account_id FROM brand_accounts WHERE brand_id = %s", (brand_id,))
        account = cursor.fetchone()
        if not account:
            return jsonify({"success": False, "message": "계정 정보를 찾을 수 없습니다."}), 404
        account_id = account['account_id']

        import json
        categories_json = json.dumps(selected_categories, ensure_ascii=False)

        cursor.execute("""
            INSERT INTO brand_subscription_categories 
            (account_id, cycle_key, selected_categories, change_count) 
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE 
            selected_categories = VALUES(selected_categories), 
            change_count = VALUES(change_count)
        """, (account_id, cycle_key, categories_json, change_count))
        conn.commit()

        return jsonify({"success": True}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/subscription/cancel-toggle', methods=['POST'])
def toggle_subscription_cancel():
    data = request.json
    brand_id = data.get('brandId')
    cancel_reserved = data.get('cancelReserved')

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT account_id FROM brand_accounts WHERE brand_id = %s", (brand_id,))
        account = cursor.fetchone()
        if not account:
            return jsonify({"success": False, "message": "계정 정보를 찾을 수 없습니다."}), 404
        account_id = account['account_id']

        cursor.execute("""
            UPDATE brand_subscriptions 
            SET cancel_reserved = %s, updated_at = NOW() 
            WHERE account_id = %s
        """, (1 if cancel_reserved else 0, account_id))
        conn.commit()

        return jsonify({"success": True}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/payment-methods/register', methods=['POST'])
def register_payment_method():
    data = request.json
    brand_id = data.get('brandId')
    card_number = data.get('cardNumber')
    card_company = data.get('cardCompany', '신용/체크카드')
    expiry_date = data.get('expiryDate')

    if not brand_id or not card_number:
        return jsonify({"success": False, "message": "카드 정보가 유효하지 않습니다."}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT account_id FROM brand_accounts WHERE brand_id = %s", (brand_id,))
        account = cursor.fetchone()
        if not account:
            return jsonify({"success": False, "message": "계정 정보를 찾을 수 없습니다."}), 404
        account_id = account['account_id']

        clean_card_num = card_number.replace('-', '').strip()
        if clean_card_num.startswith('0000'):
            return jsonify({
                "success": False, 
                "message": "등록할 수 없는 카드입니다. (100원 승인 테스트 실패: 카드 상태 및 한도를 확인해 주세요)"
            }), 400

        cursor.execute("UPDATE payment_methods SET is_default = 0 WHERE account_id = %s", (account_id,))

        masked_card_number = card_number
        if len(clean_card_num) >= 12:
            masked_card_number = f"{clean_card_num[:4]}-****-****-{clean_card_num[-4:]}"

        cursor.execute("""
            INSERT INTO payment_methods 
            (account_id, method_type, provider_name, card_number, card_company, expiry_date, is_default, created_at) 
            VALUES (%s, 'card', %s, %s, %s, %s, 1, NOW())
        """, (account_id, card_company, masked_card_number, card_company, expiry_date))

        conn.commit()
        return jsonify({
            "success": True, 
            "message": "결제 수단 검증(100원 승인 및 즉시 취소)이 완료되었으며, 대표 결제 수단으로 등록되었습니다."
        }), 200

    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/brands', methods=['GET'])
def get_all_or_search_brands():
    keyword = request.args.get('keyword', '').strip()
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if keyword:
            sql = "SELECT brand_id, brand_name, brand_code FROM brands WHERE is_active = 1 AND (brand_name LIKE %s OR brand_code LIKE %s)"
            cursor.execute(sql, (f"%{keyword}%", f"%{keyword}%"))
        else:
            sql = "SELECT brand_id, brand_name, brand_code FROM brands WHERE is_active = 1"
            cursor.execute(sql)
        brands = cursor.fetchall()
        return jsonify({"success": True, "brands": brands}), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/search-brands', methods=['GET'])
def search_brands():
    return get_all_or_search_brands()

@app.route('/api/find-email', methods=['POST'])
def find_email():
    data = request.json
    brand_id = data.get('brandId')
    name = data.get('name')

    if not brand_id or not name:
        return jsonify({"success": False, "message": "브랜드 고유번호와 담당자 이름을 입력해주세요."}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT email FROM brand_managers WHERE brand_id = %s AND name = %s",
            (brand_id, name)
        )
        manager = cursor.fetchone()
        if not manager:
            return jsonify({"success": False, "message": "일치하는 담당자 정보를 찾을 수 없습니다."}), 404
        
        email = manager['email']
        parts = email.split('@')
        masked_email = parts[0][:2] + '*' * (len(parts[0]) - 2) + '@' + parts[1] if len(parts[0]) > 2 else parts[0] + '@' + parts[1]

        return jsonify({"success": True, "maskedEmail": masked_email}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/reset-password', methods=['POST'])
def reset_password():
    data = request.json
    brand_id = data.get('brandId')
    email = data.get('email')

    if not brand_id or not email:
        return jsonify({"success": False, "message": "브랜드 고유번호와 이메일을 입력해주세요."}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT manager_id FROM brand_managers WHERE brand_id = %s AND email = %s",
            (brand_id, email)
        )
        manager = cursor.fetchone()
        if not manager:
            return jsonify({"success": False, "message": "등록된 담당자 정보와 일치하지 않습니다."}), 404

        chars = string.ascii_letters + string.digits
        temp_pw = ''.join(random.choice(chars) for _ in range(8))
        temp_pw_hash = generate_password_hash(temp_pw)

        cursor.execute(
            "UPDATE brand_managers SET manager_pw_hash = %s WHERE manager_id = %s",
            (temp_pw_hash, manager['manager_id'])
        )
        conn.commit()

        msg = MIMEText(f"안녕하세요. Oliview 임시 비밀번호가 발급되었습니다.\n\n임시 비밀번호: [{temp_pw}]\n\n로그인 후 회원정보 수정에서 비밀번호를 변경해 주세요.")
        msg['Subject'] = 'Oliview 임시 비밀번호 발급 안내'
        msg['From'] = SMTP_USER
        msg['To'] = email

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)
        server.quit()

        return jsonify({"success": True, "message": "등록된 이메일로 임시 비밀번호가 발송되었습니다."}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": f"오류 발생: {str(e)}"}), 500
    finally:
        cursor.close()
        conn.close()

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, port=5050)