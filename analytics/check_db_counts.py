import subprocess

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

res = subprocess.run(['docker', 'exec', 'bteam_db', 'mysql', '-ugp123', '-pGP123!', 'oliview_project', '-e', query], capture_output=True, text=True, encoding='utf-8', errors='ignore')
print("=== B-Team Data Counts ===")
print(res.stdout)

query_pilos = """
SELECT 'daily_document' as tbl, count(*) as cnt FROM daily_document
UNION ALL
SELECT 'sentiment_index_result', count(*) FROM sentiment_index_result
UNION ALL
SELECT 'llm_report', count(*) FROM llm_report
UNION ALL
SELECT 'stock', count(*) FROM stock;
"""

res2 = subprocess.run(['docker', 'exec', 'pilos-db', 'mysql', '-upilos_user', '-ppilos_password', 'pilos_v2', '-e', query_pilos], capture_output=True, text=True, encoding='utf-8', errors='ignore')
print("=== Pilos Data Counts ===")
print(res2.stdout)
