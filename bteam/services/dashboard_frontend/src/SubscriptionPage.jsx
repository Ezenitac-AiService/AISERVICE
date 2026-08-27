import React, { useState } from 'react';

function SubscriptionPage({ onNavigate, setSubscription, setIsCancelled, user, apiBaseUrl }) {
  const baseUrl = apiBaseUrl || '/bteam/oliview';
  const [showTermsModal, setShowTermsModal] = useState(false);
  const [showPaymentModal, setShowPaymentModal] = useState(false);
  const [showSuccessModal, setShowSuccessModal] = useState(false);
  
  const [selectedPlan, setSelectedPlan] = useState(null);
  const [paymentMethod, setPaymentMethod] = useState('kakaopay');

  const [termsAgreed, setTermsAgreed] = useState({
    service: false,
    autoPay: false
  });

  // 🌟 상단 1줄 (파란 테두리 없는 일반 플랜)
  const topPlans = [
    { 
      id: 1,
      name: '베이비', 
      price: '100,000', 
      period: '/ 월',
      badge: null,
      desc: '스타트업 및 입문 브랜드를 위한\n기본형',
      features: [
        '타사 상품 3개 선택 열람 가능',
        '매월 열람 권한 초기화',
        '전월 열람 상품 재열람 시 횟수 차감'
      ]
    },
    { 
      id: 2,
      name: '핑크', 
      price: '300,000', 
      period: '/ 월',
      badge: null,
      desc: '성장하는 브랜드를 위한\n확장형',
      features: [
        '타사 상품 7개 선택 열람 가능',
        '매월 열람 권한 초기화',
        '전월 열람 상품 재열람 시 횟수 차감'
      ]
    }
  ];

  // 🌟 하단 1줄 (파란 테두리 있는 강조 플랜)
  const bottomPlans = [
    { 
      id: 3,
      name: '그린', 
      price: '500,000', 
      period: '/ 월',
      badge: 'POPULAR',
      desc: '가장 많은 브랜드가 선택하는\n추천 요금제',
      features: [
        '타사 상품 15개 선택 열람 가능',
        '매월 열람 권한 초기화',
        '🎁 전월 열람 상품 1개 무료 재열람 혜택'
      ]
    },
    { 
      id: 4,
      name: '블랙', 
      price: '700,000', 
      period: '/ 월',
      badge: 'BEST VALUE',
      desc: '특정 카테고리를 집중 분석하는\n전문 브랜드용',
      features: [
        '타사 카테고리 1개 전상품 열람 가능',
        '카테고리 변경 시 추가금 10만원',
        '매월 카테고리 변경 횟수 1회 제한'
      ]
    },
    { 
      id: 5,
      name: '골드', 
      price: '1,000,000', 
      period: '/ 월',
      badge: 'ENTERPRISE',
      desc: '대규모 브랜드 및 카테고리\n선도 기업용',
      features: [
        '타사 카테고리 2개 전상품 무제한 열람',
        '카테고리 변경 시 추가 비용 무료',
        '매월 카테고리 변경 횟수 1회 제한'
      ]
    }
  ];

  const handleSelectPlan = (plan) => {
    setSelectedPlan(plan);
    setTermsAgreed({ service: false, autoPay: false });
    setShowTermsModal(true);
  };

  const handleProceedToPayment = () => {
    if (!termsAgreed.service || !termsAgreed.autoPay) {
      alert("모든 필수 이용약관에 동의해 주세요.");
      return;
    }
    setShowTermsModal(false);
    setShowPaymentModal(true);
  };

  const processPayment = () => {
    const { window } = globalThis;
    const IMP = window.IMP; 

    if (!IMP) {
      alert("포트원 V1 SDK가 로드되지 않았습니다.");
      return;
    }

    IMP.init('imp47567664'); 
    const amount = 100;

    let pgOption = "kakaopay";
    let payMethodOption = "card";

    if (paymentMethod === 'card') {
      pgOption = "html5_inicis.INIBillTst"; 
      payMethodOption = "card";
    } else if (paymentMethod === 'trans') {
      pgOption = "html5_inicis.INIBillTst"; 
      payMethodOption = "trans"; 
    }

    const data = {
      pg: pgOption,
      pay_method: payMethodOption, 
      merchant_uid: `mid_${new Date().getTime()}`,
      name: `${selectedPlan.name} 구독권 결제`,
      amount: amount, 
      buyer_email: user?.email || "test@example.com",
      buyer_name: user?.managerName || "담당자",
      buyer_tel: "010-1234-5678",
    };

    IMP.request_pay(data, (response) => {
      if (response.success) {
        const providerName = response.card_name || response.pg_provider || paymentMethod;
        const cardNumber = response.card_number || '****-****-****-****'; 

        fetch(`${baseUrl}/api/subscribe`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            brandId: user?.brandId, 
            planId: selectedPlan.id,         
            amount: amount,         
            paymentMethod: paymentMethod,
            providerName: providerName,
            cardNumber: cardNumber
          })
        })
        .then(res => res.json())
        .then(resData => {
          if (resData.success) {
            setShowPaymentModal(false);
            setShowSuccessModal(true); 
          } else {
            alert(`결제 실패: ${resData.message}`);
          }
        })
        .catch(err => {
          console.error("서버 통신 에러:", err);
          alert("백엔드 서버 통신 중 오류가 발생했습니다.");
        });

      } else {
        alert(`결제 실패: ${response.error_msg}`);
      }
    });
  };

  const finishSubscription = () => {
    setSubscription(selectedPlan.name); 
    setIsCancelled(false); 
    setShowSuccessModal(false);
    onNavigate('competitorDashboard'); 
  };

  // 플랜 카드 단일 렌더링 함수
  const renderCard = (plan) => {
    const isHighlighted = plan.badge !== null;
    return (
      <div 
        key={plan.id} 
        style={{
          ...styles.card,
          ...(isHighlighted ? styles.highlightedCard : {})
        }}
      >
        {plan.badge && <div style={styles.badge}>{plan.badge}</div>}
        
        <h3 style={styles.planName}>{plan.name}</h3>
        <p style={styles.planDesc}>{plan.desc}</p>
        
        <div style={styles.priceContainer}>
          <span style={styles.priceNum}>₩{plan.price}</span>
          <span style={styles.pricePeriod}>{plan.period}</span>
        </div>

        <div style={styles.divider} />

        <ul style={styles.featureList}>
          {plan.features.map((feat, idx) => (
            <li key={idx} style={styles.featureItem}>
              <span style={styles.checkIcon}>✓</span>
              <span>{feat}</span>
            </li>
          ))}
        </ul>

        <button 
          onClick={() => handleSelectPlan(plan)}
          style={{
            ...styles.selectBtn,
            ...(isHighlighted ? styles.highlightedBtn : {})
          }}
        >
          {plan.name} 플랜 시작하기
        </button>
      </div>
    );
  };

  return (
    <div style={styles.container}>
      {/* 헤더 섹션 */}
      <div style={styles.header}>
        <span style={styles.subTitle}>MEMBERSHIP PLAN</span>
        <h1 style={styles.mainTitle}>브랜드 분석 맞춤 구독 플랜</h1>
        <p style={styles.description}>
          타사 브랜드의 상품 리뷰 및 AI 감성 분석 데이터를 실시간으로 열람하세요.<br />
          언제든지 해지 가능하며, 결제 후 7일 이내 미이용 시 100% 환불됩니다(환불 신청 별도).
        </p>
      </div>

      {/* 🌟 1단: 테두리 없는 일반 플랜 (윗줄 한 줄 고정) */}
      <div style={{ ...styles.rowContainer, justifyContent: 'center' }}>
        {topPlans.map(renderCard)}
      </div>

      {/* 🌟 2단: 파란 테두리 강조 플랜 (아랫줄 한 줄 고정) */}
      <div style={{ ...styles.rowContainer, justifyContent: 'center', marginTop: '35px' }}>
        {bottomPlans.map(renderCard)}
      </div>

      <div style={{ textAlign: 'center', marginTop: '50px' }}>
        <button 
          onClick={() => onNavigate('productDetail')}
          style={styles.backBtn}
        >
          ← 내 브랜드 상품 관리로 돌아가기
        </button>
      </div>

      {/* 팝업 모달 영역 (동일) */}
      {showTermsModal && selectedPlan && (
        <div style={styles.modalOverlay}>
          <div style={styles.modalContent}>
            <h2 style={{ fontSize: '1.4rem', color: '#0f172a', marginBottom: '8px' }}>
              [{selectedPlan.name}] 구독 이용약관 동의
            </h2>
            <p style={{ fontSize: '0.9rem', color: '#64748b', marginBottom: '20px' }}>
              서비스 이용 및 정기 결제를 위해 아래 약관에 동의해 주세요.
            </p>

            <div style={styles.termsBox}>
              <h4 style={styles.termsTitle}>제 1 조 (구독 서비스의 이용)</h4>
              <p style={styles.termsText}>
                본 서비스는 월간 정기 구독형 서비스로, 선택하신 플랜에 따라 타사 브랜드 분석 권한이 제공됩니다.
              </p>
              <h4 style={styles.termsTitle}>제 2 조 (자동 결제 및 해지)</h4>
              <p style={styles.termsText}>
                매월 지정된 결제일에 자동 결제되며 언제든지 해지 신청이 가능합니다.
              </p>
              <h4 style={styles.termsTitle}>제 3 조 (환불 규정)</h4>
              <p style={styles.termsText}>
                결제 후 7일 이내 미이용 시 100% 환불 가능합니다.
              </p>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', margin: '20px 0', textAlign: 'left' }}>
              <label style={styles.checkboxLabel}>
                <input 
                  type="checkbox" 
                  checked={termsAgreed.service}
                  onChange={(e) => setTermsAgreed({ ...termsAgreed, service: e.target.checked })}
                  style={{ width: '18px', height: '18px' }}
                />
                <span><strong>[필수]</strong> Oliview 서비스 이용약관 동의</span>
              </label>

              <label style={styles.checkboxLabel}>
                <input 
                  type="checkbox" 
                  checked={termsAgreed.autoPay}
                  onChange={(e) => setTermsAgreed({ ...termsAgreed, autoPay: e.target.checked })}
                  style={{ width: '18px', height: '18px' }}
                />
                <span><strong>[필수]</strong> 정기 자동 결제 및 환불 규정 동의</span>
              </label>
            </div>

            <div style={{ display: 'flex', gap: '10px', marginTop: '25px' }}>
              <button onClick={() => setShowTermsModal(false)} style={styles.cancelBtn}>취소</button>
              <button onClick={handleProceedToPayment} style={styles.confirmBtn}>동의하고 결제 진행</button>
            </div>
          </div>
        </div>
      )}

      {showPaymentModal && selectedPlan && (
        <div style={styles.modalOverlay}>
          <div style={styles.modalContent}>
            <h2 style={{ fontSize: '1.4rem', marginBottom: '10px' }}>[{selectedPlan.name}] 결제 수단 선택</h2>
            <p style={{ fontSize: '1.3rem', fontWeight: 'bold', color: '#2563eb', marginBottom: '25px' }}>
              월 ₩{selectedPlan.price}
            </p>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginBottom: '30px' }}>
              <button
                onClick={() => setPaymentMethod('kakaopay')}
                style={{
                  ...styles.payMethodBtn,
                  border: paymentMethod === 'kakaopay' ? '2px solid #fee500' : '1px solid #e2e8f0',
                  backgroundColor: paymentMethod === 'kakaopay' ? '#fee500' : '#fff'
                }}
              >
                💛 카카오페이 간편결제
              </button>
              <button
                onClick={() => setPaymentMethod('card')}
                style={{
                  ...styles.payMethodBtn,
                  border: paymentMethod === 'card' ? '2px solid #0f172a' : '1px solid #e2e8f0',
                  backgroundColor: paymentMethod === 'card' ? '#0f172a' : '#fff',
                  color: paymentMethod === 'card' ? '#fff' : '#0f172a'
                }}
              >
                💳 신용 / 체크카드
              </button>
              <button
                onClick={() => setPaymentMethod('trans')}
                style={{
                  ...styles.payMethodBtn,
                  border: paymentMethod === 'trans' ? '2px solid #0f172a' : '1px solid #e2e8f0',
                  backgroundColor: paymentMethod === 'trans' ? '#0f172a' : '#fff',
                  color: paymentMethod === 'trans' ? '#fff' : '#0f172a'
                }}
              >
                🏦 실시간 계좌이체
              </button>
            </div>

            <div style={{ display: 'flex', gap: '10px' }}>
              <button onClick={() => setShowPaymentModal(false)} style={styles.cancelBtn}>취소</button>
              <button onClick={processPayment} style={styles.confirmBtn}>결제하기 (테스트 100원)</button>
            </div>
          </div>
        </div>
      )}

      {showSuccessModal && (
        <div style={styles.modalOverlay}>
          <div style={styles.modalContent}>
            <div style={{ fontSize: '3rem', marginBottom: '10px' }}>🎉</div>
            <h2 style={{ fontSize: '1.5rem', color: '#0f172a', marginBottom: '10px' }}>
              [{selectedPlan.name}] 구독이 시작되었습니다!
            </h2>
            <p style={{ color: '#64748b', marginBottom: '25px', fontSize: '0.95rem' }}>
              지금부터 경쟁 브랜드 상세 분석 데이터를 자유롭게 확인하실 수 있습니다.
            </p>
            <button onClick={finishSubscription} style={{ ...styles.confirmBtn, width: '100%' }}>
              경쟁사 분석 대시보드로 이동
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

const styles = {
  container: { maxWidth: '1200px', margin: '0 auto', padding: '60px 20px', fontFamily: 'sans-serif' },
  header: { textAlign: 'center', marginBottom: '40px' },
  subTitle: { fontSize: '0.85rem', fontWeight: 'bold', color: '#2563eb', letterSpacing: '1px' },
  mainTitle: { fontSize: '2.2rem', fontWeight: 'bold', color: '#0f172a', margin: '10px 0' },
  description: { fontSize: '1rem', color: '#64748b', lineHeight: '1.6' },
  
  // 🌟 한 줄 고정 및 자동 줄바꿈 방지 스타일 적용
  rowContainer: { 
    display: 'flex', 
    flexDirection: 'row', 
    flexWrap: 'nowrap', 
    gap: '20px', 
    alignItems: 'stretch',
    overflowX: 'auto',
    paddingTop: '16px',
    paddingBottom: '10px'
  },
  card: { 
    width: '260px', 
    minWidth: '260px', 
    flexShrink: 0, 
    backgroundColor: '#ffffff', 
    borderRadius: '16px', 
    padding: '30px 20px', 
    border: '1px solid #e2e8f0', 
    boxShadow: '0 4px 6px -1px rgba(0,0,0,0.05)', 
    display: 'flex', 
    flexDirection: 'column', 
    position: 'relative' 
  },
  highlightedCard: { border: '2px solid #2563eb', boxShadow: '0 10px 25px -5px rgba(37,99,235,0.15)', transform: 'translateY(-4px)' },
  badge: { position: 'absolute', top: '-12px', left: '50%', transform: 'translateX(-50%)', backgroundColor: '#2563eb', color: '#fff', fontSize: '0.75rem', fontWeight: 'bold', padding: '4px 12px', borderRadius: '20px', letterSpacing: '0.5px' },
  
  planName: { fontSize: '1.4rem', fontWeight: 'bold', color: '#0f172a', marginBottom: '6px' },
  planDesc: { fontSize: '0.82rem', color: '#64748b', height: '36px', lineHeight: '1.4', marginBottom: '15px' },
  priceContainer: { margin: '10px 0' },
  priceNum: { fontSize: '1.6rem', fontWeight: 'bold', color: '#0f172a' },
  pricePeriod: { fontSize: '0.85rem', color: '#94a3b8', marginLeft: '4px' },
  divider: { height: '1px', backgroundColor: '#f1f5f9', margin: '15px 0' },
  
  featureList: { listStyle: 'none', padding: 0, margin: '0 0 25px 0', flex: 1, textAlign: 'left' },
  featureItem: { fontSize: '0.85rem', color: '#334155', padding: '6px 0', display: 'flex', gap: '8px', lineHeight: '1.4' },
  checkIcon: { color: '#2563eb', fontWeight: 'bold' },
  
  selectBtn: { width: '100%', padding: '12px', backgroundColor: '#f1f5f9', color: '#1e293b', border: 'none', borderRadius: '8px', fontWeight: 'bold', cursor: 'pointer', fontSize: '0.9rem' },
  highlightedBtn: { backgroundColor: '#2563eb', color: '#ffffff' },
  backBtn: { padding: '12px 24px', backgroundColor: 'transparent', color: '#64748b', border: '1px solid #cbd5e1', borderRadius: '30px', fontWeight: 'bold', cursor: 'pointer' },
  
  modalOverlay: { position: 'fixed', top: 0, left: 0, width: '100vw', height: '100vh', backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', justifyContent: 'center', alignItems: 'center', zIndex: 1000 },
  modalContent: { backgroundColor: '#fff', borderRadius: '16px', padding: '30px', width: '460px', maxWidth: '90%', boxShadow: '0 20px 25px -5px rgba(0,0,0,0.1)', textAlign: 'center' },
  termsBox: { backgroundColor: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '8px', padding: '15px', maxHeight: '160px', overflowY: 'auto', textAlign: 'left', marginBottom: '15px' },
  termsTitle: { fontSize: '0.85rem', fontWeight: 'bold', color: '#1e293b', margin: '8px 0 4px 0' },
  termsText: { fontSize: '0.8rem', color: '#64748b', margin: 0, lineHeight: '1.4' },
  checkboxLabel: { fontSize: '0.9rem', color: '#334155', display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' },
  
  payMethodBtn: { width: '100%', padding: '12px', borderRadius: '8px', fontWeight: 'bold', cursor: 'pointer', fontSize: '0.95rem' },
  cancelBtn: { flex: 1, padding: '12px', backgroundColor: '#e2e8f0', color: '#334155', border: 'none', borderRadius: '8px', fontWeight: 'bold', cursor: 'pointer' },
  confirmBtn: { flex: 1, padding: '12px', backgroundColor: '#2563eb', color: '#fff', border: 'none', borderRadius: '8px', fontWeight: 'bold', cursor: 'pointer' }
};

export default SubscriptionPage;