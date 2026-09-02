import React, { useState, useEffect } from 'react';
import './MainPage.css';

function MainPage({ onNavigate, isLoggedIn, subscription }) {
  // 1. 메인 롤링 슬라이더 이미지
  const cosmeticImages = [
    "https://i.pinimg.com/1200x/bf/c5/a1/bfc5a19c1ce97629f8f6a561d8b2df5f.jpg",
    "https://i.pinimg.com/1200x/f6/fd/e2/f6fde252bcedeef4f60bc72d9c55cde2.jpg",
    "https://i.pinimg.com/736x/d8/c7/9c/d8c79c9df5b09eae42ed6368ea65b4ce.jpg",
    "https://i.pinimg.com/736x/2f/43/d4/2f43d432db6c7829140e9a1a6cb53ad3.jpg",
    "https://i.pinimg.com/736x/06/ef/5b/06ef5bb475af2a07d539cc77cfe34dfa.jpg",
    "https://i.pinimg.com/1200x/29/a7/8c/29a78cdf99d788ca2df90e6ad89e679f.jpg",
    "https://i.pinimg.com/1200x/9a/1d/6b/9a1d6b779b211ec7d192d5055dfa18d6.jpg"
  ];

  // 2. 가상 브랜드와 상품 데이터
  const brandGroups = [
    {
      brandName: "식물나라 (SHINGMULNARA)",
      products: [
        { name: "식물나라 뽀얀쌀 수분 선크림", imgUrl: "https://image.oliveyoung.co.kr/cfimages/cf-goods/uploads/images/thumbnails/10/0000/0021/A00000021733005ko.jpg?l=ko&QT=85&SF=webp&sharpen=1x0.5" },
        { name: "식물나라 어린녹차 촉촉 진정토너", imgUrl: "https://image.oliveyoung.co.kr/cfimages/cf-goods/uploads/images/thumbnails/10/0000/0020/A00000020317102ko.jpg?l=ko&QT=85&SF=webp&sharpen=1x0.5" },
        { name: "식물나라 뽀얀쌀 생기 톤업 선 쿠션", imgUrl: "https://image.oliveyoung.co.kr/cfimages/cf-goods/uploads/images/thumbnails/10/0000/0021/A00000021767903ko.jpg?l=ko&QT=85&SF=webp&sharpen=1x0.5" },
        { name: "식물나라 어린녹차 촉촉 버블 클렌저", imgUrl: "https://image.oliveyoung.co.kr/cfimages/cf-goods/uploads/images/thumbnails/10/0000/0025/A00000025867301ko.jpg?l=ko&QT=85&SF=webp&sharpen=1x0.5" }
      ]
    },
    {
      brandName: "컬러그램 (COLORGRAM)",
      products: [
        { name: "컬러그램 누디 블러 틴트", imgUrl: "https://image.oliveyoung.co.kr/cfimages/cf-goods/uploads/images/thumbnails/10/0000/0023/A00000023058116ko.jpg?l=ko&QT=85&SF=webp&sharpen=1x0.5" },
        { name: "컬러그램 싱글 큐브 섀도우", imgUrl: "https://image.oliveyoung.co.kr/cfimages/cf-goods/uploads/images/thumbnails/10/0000/0021/A00000021666707ko.jpg?l=ko&QT=85&SF=webp&sharpen=1x0.5" },
        { name: "컬러그램 누디 블러 립펜슬", imgUrl: "https://image.oliveyoung.co.kr/cfimages/cf-goods/uploads/images/thumbnails/10/0000/0023/A00000023832408ko.jpg?l=ko&QT=85&SF=webp&sharpen=1x0.5" },
        { name: "컬러그램 말랑 젤리 스틱", imgUrl: "https://image.oliveyoung.co.kr/cfimages/cf-goods/uploads/images/thumbnails/10/0000/0023/A00000023645303ko.jpg?l=ko&QT=85&SF=webp&sharpen=1x0.5" }
      ]
    },
    {
      brandName: "브링그린 (BRING GREEN)",
      products: [
        { name: "브링그린 징크테카 트러블 세럼", imgUrl: "https://image.oliveyoung.co.kr/cfimages/cf-goods/uploads/images/thumbnails/10/0000/0020/A00000020064699ko.jpg?l=ko&QT=85&SF=webp&sharpen=1x0.5" },
        { name: "브링그린 티트리 시카 쿨링 선스틱", imgUrl: "https://image.oliveyoung.co.kr/cfimages/cf-goods/uploads/images/thumbnails/10/0000/0020/A00000020119339ko.jpg?l=ko&QT=85&SF=webp&sharpen=1x0.5" },
        { name: "브링그린 티트리 시카 딥클렌징 오일", imgUrl: "https://image.oliveyoung.co.kr/cfimages/cf-goods/uploads/images/thumbnails/10/0000/0021/A00000021481506ko.jpg?l=ko&QT=85&SF=webp&sharpen=1x0.5" },
        { name: "브링그린 블루빈 B5-PDRN 마일드 크림", imgUrl: "https://image.oliveyoung.co.kr/cfimages/cf-goods/uploads/images/thumbnails/10/0000/0023/A00000023438403ko.jpg?l=ko&QT=85&SF=webp&sharpen=1x0.5" }
      ]
    }
  ];

  // 3. 개선점 분석 예시 데이터 (그래프 수치 및 요약 문구)
  const analysisData = [
    {
      productName: "A사 매트 파운데이션",
      scores: [40, 90, 20, 80, 70],
      summary: "생각보다 꾸덕해서 발림성이 좋지 않다는 평이 많습니다.\n반면 땀에 강해 지속력과 밀착력은 우수하다는 평가를 받았습니다."
    },
    {
      productName: "B사 워터 립 틴트",
      scores: [90, 30, 40, 95, 50],
      summary: "발림성이 매우 부드럽고 발색력이 뛰어나다는 평이 압도적입니다.\n다만 식사 후 색이 금방 지워져 지속력이 다소 아쉽다는 의견이 있습니다."
    }
  ];

  // ⭐️ 4. 타사 비교 분석 예시 데이터 (좌우 양쪽 요약)
  const compareData = [
    {
      left: {
        brand: "에스쁘아 (espoir)",
        productName: "비글로우 볼륨 쿠션",
        summary: "자연스러운 광채와 매끄러운 피부 표현이 장점입니다.\n하지만 커버력이 다소 약하다는 의견이 있습니다."
      },
      right: {
        brand: "롬앤 (rom&nd)",
        productName: "누 제로 쿠션",
        summary: "보송한 마무리감과 높은 커버력으로 지성 피부에 추천됩니다.\n다만 건성 피부에는 건조할 수 있다는 평이 있습니다."
      }
    },
    {
      left: {
        brand: "클리오 (CLIO)",
        productName: "킬커버 더 뉴 파운웨어",
        summary: "압도적인 커버력과 지속력으로 오랜 시간 화장이 유지됩니다.\n두껍게 발릴 수 있어 양 조절이 필수적입니다."
      },
      right: {
        brand: "어뮤즈 (AMUSE)",
        productName: "듀 젤리 비건 쿠션",
        summary: "투명하고 맑은 수분광이 돌아 피부가 좋아 보입니다.\n마스크 묻어남이 다소 아쉽다는 리뷰가 많습니다."
      }
    }
  ];

  const [currentBrandIndex, setCurrentBrandIndex] = useState(0);
  const [currentAnalysisIndex, setCurrentAnalysisIndex] = useState(0);
  const [currentCompareIndex, setCurrentCompareIndex] = useState(0); // 비교 데이터 타이머용

  // 브랜드 탭 애니메이션 타이머
  useEffect(() => {
    const interval = setInterval(() => setCurrentBrandIndex((prev) => (prev + 1) % brandGroups.length), 2500);
    return () => clearInterval(interval);
  }, []);

  // 감정 분석 탭 애니메이션 타이머
  useEffect(() => {
    const interval = setInterval(() => setCurrentAnalysisIndex((prev) => (prev + 1) % analysisData.length), 2000);
    return () => clearInterval(interval);
  }, []);

  // ⭐️ 타사 비교 분석 애니메이션 타이머 (2.5초)
  useEffect(() => {
    const interval = setInterval(() => setCurrentCompareIndex((prev) => (prev + 1) % compareData.length), 2500);
    return () => clearInterval(interval);
  }, []);

  // 오각형(레이더 차트) 좌표 계산 함수
  const getPolygonPoints = (data) => {
    const angles = [0, 72, 144, 216, 288];
    return data.map((val, i) => {
      const r = (val / 100) * 40;
      const angle = (angles[i] * Math.PI) / 180;
      const x = 60 + r * Math.sin(angle);
      const y = 60 - r * Math.cos(angle);
      return `${x},${y}`;
    }).join(' ');
  };

  const handleCompetitorClick = () => {
    // [선택 사항] 비로그인 시 처리
    if (!isLoggedIn) {
      alert('로그인이 필요합니다.');
      onNavigate('login');
      return;
    }

    // 구독 정보가 있으면 타사 대시보드로, 없으면 구독 페이지로 이동
    if (subscription) {
      onNavigate('competitorDashboard');
    } else {
      onNavigate('subscription');
    }
  };

  const handleMyBrandClick = () => {
    if (!isLoggedIn) {
      alert('로그인이 필요합니다.');
      onNavigate('login');
      return;
    }
    onNavigate('myBrand');
  };

  return (
    <div className="main-container">

      <section className="section hero-section">
        <div className="hero-titles">
          <h1>OLIVIEW<br/>PROJECT</h1>
          <h2>by<br/>Olive Young</h2>
        </div>
        <div className="hero-images-slider">
          <div className="slider-track">
            {[...cosmeticImages, ...cosmeticImages].map((imgUrl, index) => (
              <div className="slider-item" key={index}>
                <img src={imgUrl} alt={`cosmetic-${index}`} />
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="section info-section">
        <div className="text-content">
          <h2>브랜드의 가치<br/>올리브영과 같이</h2>
          <p>브랜드의 가치는 상품이 좌우합니다.<br/>브랜드의 가치를 높이는 일, 올리브영이 함께하겠습니다.</p>
        </div>
        <div className="image-content">
          <div className="review-animation-container">
            <div className="review-card card-1">
              <img src="https://i.pinimg.com/1200x/7e/ff/a1/7effa17dbc351ef1785824df54e4413f.jpg" alt="review1" />
              <div className="review-tag"><span style={{ color: '#ef4444' }}>★★★★★</span><br/>"수분감이 미쳤어요! 💦 인생템 등극!"</div>
            </div>
            <div className="review-card card-2">
              <img src="https://i.pinimg.com/736x/72/c3/9e/72c39e8bffe7b39f8c971c8af84cedd6.jpg" alt="review2" />
              <div className="review-tag"><span style={{ color: '#ef4444' }}>★★★★★</span><br/>"커버력 최고 ㅠㅠ 제발 써주세요!! ✨"</div>
            </div>
            <div className="review-card card-3">
              <img src="https://i.pinimg.com/1200x/93/2d/e9/932de950aa5dc81ff0f7e4996f513955.jpg" alt="review3" />
              <div className="review-tag"><span style={{ color: '#ef4444' }}>★★★★☆</span><br/>"세정력 짱! 살짝 당김 있지만 그래도 좋아요!"</div>
            </div>
          </div>
        </div>
      </section>

      <section className="section my-brand-section">
        <h2>내 브랜드 상품을 모아 볼 수 있습니다.</h2>
        <h3 className="dynamic-brand-name" style={{ marginBottom: '40px'}}>{brandGroups[currentBrandIndex].brandName }</h3>
        <div className="product-grid fade-in-slide-up" key={`brand-${currentBrandIndex}`}>
          {brandGroups[currentBrandIndex].products.map((item, idx) => (
            <div className="product-card" key={idx}>
              <div className="product-card-img">
                {item.imgUrl ? <img src={item.imgUrl} alt={item.name} /> : <span>사진 영역</span>}
              </div>
              <div className="product-card-name">{item.name}</div>
            </div>
          ))}
        </div>
      </section>

      <section className="section analysis-section">
        <h2 style={{ marginBottom: '40px'}}>소비자의 리뷰를 통해 선택한 상품의 개선점을 확인할 수 있습니다.</h2>
        <div className="analysis-content">
          <div className="emotion-chart">
            <svg viewBox="0 0 120 120" style={{ width: '80%', height: '80%', overflow: 'visible' }}>
              {[100, 80, 60, 40, 20].map((level, i) => (
                <polygon key={i} points={getPolygonPoints([level, level, level, level, level])} fill="none" stroke="#ddd" strokeWidth="0.5" />
              ))}
              {[0, 72, 144, 216, 288].map((angle, i) => {
                const rad = (angle * Math.PI) / 180;
                return <line key={i} x1="60" y1="60" x2={60 + 40 * Math.sin(rad)} y2={60 - 40 * Math.cos(rad)} stroke="#ddd" strokeWidth="0.5" />;
              })}
              <polygon points={getPolygonPoints(analysisData[currentAnalysisIndex].scores)} fill="rgba(139, 92, 246, 0.4)" stroke="#8b5cf6" strokeWidth="2" style={{ transition: 'all 0.8s cubic-bezier(0.4, 0, 0.2, 1)' }} />
              <text x="60" y="14" fontSize="4.5" textAnchor="middle" fill="#555" fontWeight="bold">발림성</text>
              <text x="104" y="48" fontSize="4.5" textAnchor="start" fill="#555" fontWeight="bold">지속력</text>
              <text x="86" y="102" fontSize="4.5" textAnchor="start" fill="#555" fontWeight="bold">자극성</text>
              <text x="34" y="102" fontSize="4.5" textAnchor="end" fill="#555" fontWeight="bold">발색력</text>
              <text x="16" y="48" fontSize="4.5" textAnchor="end" fill="#555" fontWeight="bold">밀착력</text>
            </svg>
          </div>
          <div className="ai-summary">
            <div key={`analysis-${currentAnalysisIndex}`} className="fade-in-slide-up" style={{ textAlign: 'left', width: '100%' }}>
              <span style={{ display: 'inline-block', backgroundColor: '#e2e8f0', color: '#475569', padding: '5px 12px', borderRadius: '20px', fontSize: '0.8rem', fontWeight: 'bold', marginBottom: '15px' }}>
                {analysisData[currentAnalysisIndex].productName}
              </span>
              <h3 style={{ fontSize: '1.2rem', color: '#111', marginBottom: '15px', lineHeight: '1.5', whiteSpace: 'pre-line' }}>
                {analysisData[currentAnalysisIndex].summary}
              </h3>
            </div>
          </div>
        </div>
      </section>

      {/* ⭐️ 타사 비교 분석 섹션 (양쪽 요약 카드로 변경됨) */}
      <section className="section compare-section">
        <h2>타사의 상품과 비교 분석이 가능합니다.</h2>
        <p style={{ marginBottom: '40px', color: '#666' }}>별도의 구독 이용권 결제가 필요합니다.</p>
        <div className="compare-content">
          
          {/* 왼쪽 A사 요약 */}
          <div className="ai-summary compare-card">
            <div key={`compare-left-${currentCompareIndex}`} className="fade-in-slide-up" style={{ textAlign: 'left', width: '100%' }}>
              <span style={{ display: 'inline-block', backgroundColor: '#e0e7ff', color: '#4338ca', padding: '5px 12px', borderRadius: '20px', fontSize: '0.8rem', fontWeight: 'bold', marginBottom: '15px' }}>
                {compareData[currentCompareIndex].left.brand}
              </span>
              <h4 style={{ fontSize: '1.1rem', marginBottom: '15px', color: '#111' }}>
                {compareData[currentCompareIndex].left.productName}
              </h4>
              <p style={{ fontSize: '1rem', color: '#333', lineHeight: '1.6', whiteSpace: 'pre-line', margin: 0 }}>
                {compareData[currentCompareIndex].left.summary}
              </p>
            </div>
          </div>

          {/* 오른쪽 B사 요약 */}
          <div className="ai-summary compare-card">
            <div key={`compare-right-${currentCompareIndex}`} className="fade-in-slide-up" style={{ textAlign: 'left', width: '100%' }}>
              <span style={{ display: 'inline-block', backgroundColor: '#fce7f3', color: '#be185d', padding: '5px 12px', borderRadius: '20px', fontSize: '0.8rem', fontWeight: 'bold', marginBottom: '15px' }}>
                {compareData[currentCompareIndex].right.brand}
              </span>
              <h4 style={{ fontSize: '1.1rem', marginBottom: '15px', color: '#111' }}>
                {compareData[currentCompareIndex].right.productName}
              </h4>
              <p style={{ fontSize: '1rem', color: '#333', lineHeight: '1.6', whiteSpace: 'pre-line', margin: 0 }}>
                {compareData[currentCompareIndex].right.summary}
              </p>
            </div>
          </div>

        </div>
      </section>

      <section className="section bottom-cta-section" style={{ borderBottom: 'none', paddingBottom: '100px' }}>
        {!isLoggedIn ? (
          <>
            <h2>서비스를 이용하려면 로그인/회원가입이 필요합니다</h2>
            <button className="login-btn" onClick={() => onNavigate('login')}>
              로그인 / 회원가입 하러 가기
            </button>
          </>
        ) : (
          <>
            <h2>환영합니다! 올리뷰의 다양한 서비스를 이용해보세요.</h2>
            <div style={{ display: 'flex', gap: '20px', justifyContent: 'center', marginTop: '30px' }}>
              <button onClick={() => onNavigate('myBrand')} style={{ padding: '20px 40px', fontSize: '1.2rem', fontWeight: 'bold', color: '#fff', backgroundColor: '#111', border: 'none', borderRadius: '30px', cursor: 'pointer' }}>
                내 상품 보러가기
              </button>
              <button 
                // ⭐️ 구독(subscription) 정보가 있으면 대시보드로, 없으면 결제/구독 페이지로 이동
                onClick={() => subscription ? onNavigate('competitorDashboard') : onNavigate('subscription')} 
                style={{ padding: '20px 40px', fontSize: '1.2rem', fontWeight: 'bold', color: '#111', backgroundColor: '#fff', border: '2px solid #111', borderRadius: '30px', cursor: 'pointer' }}>
                타사제품 보러가기
              </button>
            </div>
          </>
        )}
      </section>
    </div>
  );
}

export default MainPage;