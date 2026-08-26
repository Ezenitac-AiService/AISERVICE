import pandas as pd

df = pd.read_csv("test_output/review_test_3_products.csv", encoding="utf-8-sig")

print("전체 행 수 :", len(df))
print("고유 review_id :", df["review_id"].nunique())
print(df["product_id"].value_counts())
print(
    df.groupby("product_id")["product_option_id"]
      .apply(lambda x: x.isna().sum())
)

# 전체 행 수 : 541
# 고유 review_id : 541
# product_id
# 3    297
# 1    232
# 2     12
# Name: count, dtype: int64
# product_id
# 1      0
# 2      0
# 3    297
# Name: product_option_id, dtype: int64