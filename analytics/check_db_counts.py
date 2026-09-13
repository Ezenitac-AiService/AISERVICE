import os
import subprocess

bteam_user = os.getenv("BTEAM_DB_USER", "gp123")
bteam_pass = os.getenv("BTEAM_DB_PASSWORD", "")

query = """
SELECT 'brand_accounts' as tbl, count(*) as cnt FROM brand_accounts
UNION ALL
SELECT 'brand_subscriptions', count(*) FROM brand_subscriptions
UNION ALL
SELECT 'competitor_product_views', count(*) FROM competitor_product_views
UNION ALL
SELECT 'brands', count(*) FROM brands
UNION ALL
SELECT 'products', count(*) FROM products
UNION ALL
SELECT 'reviews', count(*) FROM reviews;
"""

cmd_bteam = ['docker', 'exec', 'bteam_db', 'mysql', f'-u{bteam_user}']
if bteam_pass:
    cmd_bteam.append(f'-p{bteam_pass}')
cmd_bteam.extend(['oliview_project', '-e', query])

res = subprocess.run(cmd_bteam, capture_output=True, text=True, encoding='utf-8', errors='ignore')
print("=== B-Team Data Counts ===")
print(res.stdout)

pilos_user = os.getenv("PILOS_DB_USER", "pilos_user")
pilos_pass = os.getenv("PILOS_DB_PASSWORD", "")

query_pilos = """
SELECT 'daily_document' as tbl, count(*) as cnt FROM daily_document
UNION ALL
SELECT 'sentiment_index_result', count(*) FROM sentiment_index_result
UNION ALL
SELECT 'llm_report', count(*) FROM llm_report
UNION ALL
SELECT 'stock', count(*) FROM stock;
"""

cmd_pilos = ['docker', 'exec', 'pilos-db', 'mysql', f'-u{pilos_user}']
if pilos_pass:
    cmd_pilos.append(f'-p{pilos_pass}')
cmd_pilos.extend(['pilos_v2', '-e', query_pilos])

res2 = subprocess.run(cmd_pilos, capture_output=True, text=True, encoding='utf-8', errors='ignore')
print("=== Pilos Data Counts ===")
print(res2.stdout)
