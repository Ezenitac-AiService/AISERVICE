import os
import shutil
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

DB_PATH = r"C:\chroma_test"

if os.path.exists(DB_PATH):
    shutil.rmtree(DB_PATH)

embeddings = HuggingFaceEmbeddings(
    model_name=r"C:\Users\MYCOM\Desktop\2차 팀프로젝트\Oliview_chatbot\models\embeddings\bge-m3",
    model_kwargs={"device": "cpu"},
    encode_kwargs={"normalize_embeddings": True},
)

texts = [
    "촉촉해서 보습력이 좋다.",
    "세정력이 우수하다.",
    "발림성이 부드럽다."
]

metadatas = [
    {"id": 1},
    {"id": 2},
    {"id": 3},
]

print("DB 생성 시작")

db = Chroma.from_texts(
    texts=texts,
    embedding=embeddings,
    metadatas=metadatas,
    persist_directory=DB_PATH,
)

print("생성 완료")

docs = db.similarity_search("보습")

print("검색 성공")
print(docs[0].page_content)