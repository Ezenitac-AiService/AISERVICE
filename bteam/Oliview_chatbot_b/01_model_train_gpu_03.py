#💡 KcELECTRA GPU 가속 파인튜닝 학습 스크립트 (12개 속성 및 Best Model 저장 기능 통합본)
import os
import torch
import json
from torch.utils.data import Dataset, DataLoader
from transformers import AutoTokenizer, AutoModelForSequenceClassification, get_linear_schedule_with_warmup
from sklearn.model_selection import train_test_split
from tqdm import tqdm
import glob

# 1. GPU(CUDA) 환경 확인 및 디바이스 자동 설정
if "CUDA_VISIBLE_DEVICES" in os.environ:
    del os.environ["CUDA_VISIBLE_DEVICES"]

print("PyTorch 버전:", torch.__version__)
print("GPU(CUDA) 사용 가능 여부:", torch.cuda.is_available())

if torch.cuda.is_available():
    DEVICE = torch.device("cuda")
    print(f"사용 예정 GPU 장치: {torch.cuda.get_device_name(0)}")
else:
    DEVICE = torch.device("cpu")
    print("⚠️ GPU를 찾을 수 없어 CPU 환경으로 구동합니다.")

# 2. 하이퍼파라미터 설정
MODEL_NAME = "beomi/KcELECTRA-base-v2022"
MAX_LEN = 128
BATCH_SIZE = 32  # GPU 가속을 위해 배치 크기를 32로 유지 (OOM 발생 시 16으로 조정)
EPOCHS = 4       
LEARNING_RATE = 5e-5
OUTPUT_DIR = "./cosmetic_kcelectra_model" # 모델 저장 경로 설정

# 3. 데이터 가공 헬퍼 함수 (지정 속성 12개 필터링)
def prepare_training_data(raw_data_list):
    sentences = []
    labels = []
    
    # AIHub 데이터 명세에 맞춘 정확한 극성 매핑
    polarity_map = {"-1": 0, "1": 1} 

    # 학습 대상이 되는 12가지 지정 속성 리스트
    target_aspects = {
        "가격","디자인","기능/효과", "사이즈/두께","색상","성분","용기","용량/개수","유통기한","제품구성","보습력/수분감", "발림성", "자극성", "세정력",
        "탄력","품질", "피부타입","지속력/유지력","흡수력","발색력", "커버력", "밀착력/접착력", "사용감", "윤기/피부(톤)", "향", "제형"
    }
    
    # 속성별 데이터 카운트를 위한 딕셔너리
    aspect_counts = {aspect: 0 for aspect in target_aspects}

    for data in raw_data_list:
        raw_text = data.get("RawText", "").strip()
        if not raw_text:
            continue
            
        for aspect in data.get("Aspects", []):
            aspect_name = aspect.get("Aspect", "").strip()
            polarity = str(aspect.get("SentimentPolarity")).strip()
            
            # 1. 요청하신 12개 확장 속성에 포함되지 않는 경우 제외
            if aspect_name not in target_aspects:
                continue
                
            # 2. 긍정(1) / 부정(-1)이 아닌 중립(0) 등의 데이터는 이진 분류를 위해 제외
            if polarity not in polarity_map:
                continue
                
            # [KcELECTRA ABSA 포맷 구현]
            input_text = f"[{aspect_name}] {raw_text}"
            
            sentences.append(input_text)
            labels.append(polarity_map[polarity])
            
            # 통계 기록
            aspect_counts[aspect_name] += 1
            
    # 속성별 데이터 분포 출력 (데이터 불균형 확인용)
    print("\n[데이터 통계] 지정된 12개 속성별 추출 건수:")
    for asp, count in aspect_counts.items():
        print(f" - {asp}: {count}건")
    print("-" * 40)
            
    return sentences, labels

# 4. PyTorch Custom Dataset 정의
class ReviewDataset(Dataset):
    def __init__(self, texts, labels, tokenizer, max_len):
        self.texts = texts
        self.labels = labels
        self.tokenizer = tokenizer
        self.max_len = max_len
        
    def __len__(self):
        return len(self.texts)
    
    def __getitem__(self, item):
        text = str(self.texts[item])
        label = self.labels[item]
        
        encoding = self.tokenizer(
            text,
            add_special_tokens=True,
            max_length=self.max_len,
            return_token_type_ids=False,
            padding='max_length',
            truncation=True,
            return_attention_mask=True,
            return_tensors='pt',
        )
        
        return {
            'review_text': text,
            'input_ids': encoding['input_ids'].flatten(),
            'attention_mask': encoding['attention_mask'].flatten(),
            'labels': torch.tensor(label, dtype=torch.long)
        }

# 5. 메인 학습 파이프라인
def train_model(base_data_folder):
    all_raw_data = []
    
    if not os.path.exists(base_data_folder):
        print(f"[오류] 입력하신 경로가 존재하지 않습니다: {base_data_folder}")
        return
        
    json_pattern_lower = os.path.join(base_data_folder, "**", "*.json")
    json_pattern_upper = os.path.join(base_data_folder, "**", "*.JSON")
    json_files = glob.glob(json_pattern_lower, recursive=True) + glob.glob(json_pattern_upper, recursive=True)
    
    print(f"[시스템] 총 {len(json_files)}개의 라벨링 데이터 파일을 발견했습니다.")
    
    if len(json_files) == 0:
        return
        
    for file_path in json_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    all_raw_data.extend(data)
                else:
                    all_raw_data.append(data)
        except Exception as e:
            print(f"[경고] {os.path.basename(file_path)} 파일 로드 실패: {e}")
            
    print(f"[시스템] 총 {len(all_raw_data)}건의 파일 데이터 파싱 완료.")
    
    # 12개 지정 특성 기준으로 데이터 추출
    texts, labels = prepare_training_data(all_raw_data)
    print(f"[시스템] 12개 속성 필터링 후 최종 변환된 학습용 데이터 수: {len(texts)}건")
    
    if len(texts) == 0:
        print("[오류] 지정한 12개 속성에 부합하는 유효한 긍정/부정 데이터가 없습니다. 속성명을 다시 확인하세요.")
        return

    # 학습/검증 데이터 분리 (8:2)
    train_texts, val_texts, train_labels, val_labels = train_test_split(
        texts, labels, test_size=0.2, random_state=42, stratify=labels  
    )
    
    print(f"[시스템] {MODEL_NAME} 토크나이저 및 모델을 로드합니다.")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    
    # 2중 분류 설정 (0=부정, 1=긍정)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME, num_labels=2)
    model = model.to(DEVICE)  
    
    train_dataset = ReviewDataset(train_texts, train_labels, tokenizer, MAX_LEN)
    val_dataset = ReviewDataset(val_texts, val_labels, tokenizer, MAX_LEN)
    
    train_loader = DataLoader(train_dataset, batch_size=BATCH_SIZE, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=BATCH_SIZE)
    
    optimizer = torch.optim.AdamW(model.parameters(), lr=LEARNING_RATE)
    total_steps = len(train_loader) * EPOCHS
    scheduler = get_linear_schedule_with_warmup(
        optimizer, num_warmup_steps=int(total_steps * 0.1), num_training_steps=total_steps
    )
    loss_fn = torch.nn.CrossEntropyLoss().to(DEVICE)
    
    # [추가] 최고 검증 정확도 및 베스트 에폭 추적용 변수 선언
    best_val_acc = 0.0
    best_epoch = 0
    
    print("[시스템] GPU 파인튜닝 가속 학습을 시작합니다.")
    for epoch in range(EPOCHS):
        model.train()
        total_train_loss = 0
        correct_predictions = 0
        
        for batch in tqdm(train_loader, desc=f"Epoch {epoch + 1}/{EPOCHS}"):
            input_ids = batch['input_ids'].to(DEVICE)
            attention_mask = batch['attention_mask'].to(DEVICE)
            labels = batch['labels'].to(DEVICE)
            
            outputs = model(input_ids=input_ids, attention_mask=attention_mask)
            _, preds = torch.max(outputs.logits, dim=1)
            loss = loss_fn(outputs.logits, labels)
            
            correct_predictions += torch.sum(preds == labels)
            total_train_loss += loss.item()
            
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()
            scheduler.step()
            optimizer.zero_grad()
            
        train_acc = correct_predictions.double() / len(train_dataset)
        train_loss = total_train_loss / len(train_loader)
        print(f"Epoch {epoch + 1} - Train Loss: {train_loss:.4f}, Train Acc: {train_acc:.4f}")
        
        # 검증 루프 (Validation)
        model.eval()
        val_correct = 0
        with torch.no_grad():
            for batch in val_loader:
                input_ids = batch['input_ids'].to(DEVICE)
                attention_mask = batch['attention_mask'].to(DEVICE)
                labels = batch['labels'].to(DEVICE)
                
                outputs = model(input_ids=input_ids, attention_mask=attention_mask)
                _, preds = torch.max(outputs.logits, dim=1)
                val_correct += torch.sum(preds == labels)
                
        val_acc = val_correct.double() / len(val_dataset)
        print(f"Epoch {epoch + 1} - Validation Acc: {val_acc:.4f}")
        
        # [수정] 최고 검증 정확도(Best Validation Accuracy) 판단 및 자동 저장 로직
        if val_acc > best_val_acc:
            best_val_acc = val_acc
            best_epoch = epoch + 1
            
            # 최고점을 경신했을 때만 모델 파일과 토크나이저를 디스크에 저장
            model.save_pretrained(OUTPUT_DIR)
            tokenizer.save_pretrained(OUTPUT_DIR)
            print(f"🔥 [최고 성능 경신] Epoch {best_epoch} 모델이 '{OUTPUT_DIR}'에 임시 저장되었습니다. (Best Acc: {best_val_acc:.4f})")
        print("-" * 50)
        
    print(f"\n[시스템] 전 에폭 학습 완료! 🏆 최적의 검증 성능을 보인 Epoch {best_epoch} (정확도: {best_val_acc:.4f}) 모델이 최종 저장되었습니다.")

if __name__ == "__main__":
    DATA_PATH = "./datas"
    train_model(DATA_PATH)
