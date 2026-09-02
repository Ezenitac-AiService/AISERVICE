import React, { useState, useEffect } from 'react';

function MySubscriptionPage({ onNavigate, user, apiBaseUrl, refreshUserStatus }) {
  const [subInfo, setSubInfo] = useState(null);
  const [paymentMethod, setPaymentMethod] = useState(null);
  const [history, setHistory] = useState([]);
  const [selectedReceipt, setSelectedReceipt] = useState(null); 
  const [isLoading, setIsLoading] = useState(true);

  // 결제 수단 등록 모달 상태
  const [isPaymentModalOpen, setIsPaymentModalOpen] = useState(false);
  const [cardForm, setCardForm] = useState({
    cardCompany: 'KB국민카드',
    cardNumber: '',
    expiryDate: '',
    cvc: ''
  });
  const [isSubmitting, setIsSubmitting] = useState(false);

  // 🌟 localStorage -> sessionStorage로 변경
  const brandId = user?.brandId || JSON.parse(sessionStorage.getItem('oliview_user'))?.brandId;
  const baseUrl = apiBaseUrl || '';

  const loadSubscriptionData = () => {
    if (brandId) {
      fetch(`${baseUrl}/api/subscription/${brandId}`)
        .then(res => res.json())
        .then(data => {
          if (data.success) {
            setSubInfo(data.subscription);
            setPaymentMethod(data.payment_method);
            setHistory(data.history || []);

            if (refreshUserStatus) {
              refreshUserStatus();
            }
          }
          setIsLoading(false);
        })
        .catch(err => {
          console.error("구독 정보 로드 실패:", err);
          setIsLoading(false);
        });
    }
  };

  useEffect(() => {
    loadSubscriptionData();
  }, [brandId, baseUrl]);

  // 구독 해지 신청 및 취소
  const handleCancelToggle = () => {
    if (!subInfo || !subInfo.nextBillingDate) return;

    const isCurrentlyReserved = subInfo.cancelReserved;
    const nextBillingDateObj = new Date(subInfo.nextBillingDate);
    nextBillingDateObj.setDate(nextBillingDateObj.getDate() - 1);

    const year = nextBillingDateObj.getFullYear();
    const month = nextBillingDateObj.getMonth() + 1;
    const day = nextBillingDateObj.getDate();

    const message = isCurrentlyReserved
      ? "구독 해지 신청을 취소하시겠습니까?\n취소하시면 다음 결제일에 정상적으로 자동 결제가 유지됩니다."
      : `정말 구독을 해지하시겠습니까?\n해지하시더라도 다음 결제 전일인 ${year}년 ${month}월 ${day}일까지 기존과 동일하게 이용 가능하며, 이후 자동 결제되지 않습니다.`;

    if (window.confirm(message)) {
      fetch(`${baseUrl}/api/subscription/cancel-toggle`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          brandId: brandId,
          cancelReserved: !isCurrentlyReserved
        })
      })
      .then(res => res.json())
      .then(data => {
        if (data.success) {
          alert(isCurrentlyReserved ? "해지 신청이 취소되었습니다." : "구독 해지가 예약되었습니다.");
          setSubInfo({ ...subInfo, cancelReserved: !isCurrentlyReserved });
        } else {
          alert(`처리 실패: ${data.message}`);
        }
      })
      .catch(err => console.error('통신 에러:', err));
    }
  };

  // 카드 등록 모달 제출
  const handleRegisterCard = (e) => {
    e.preventDefault();
    if (!cardForm.cardNumber || !cardForm.expiryDate) {
      alert("카드 번호와 유효기간을 입력해주세요.");
      return;
    }

    setIsSubmitting(true);

    fetch(`${baseUrl}/api/payment-methods/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        brandId: brandId,
        cardCompany: cardForm.cardCompany,
        cardNumber: cardForm.cardNumber,
        expiryDate: cardForm.expiryDate
      })
    })
    .then(res => res.json())
    .then(data => {
      setIsSubmitting(false);
      if (data.success) {
        alert(data.message);
        setIsPaymentModalOpen(false);
        setCardForm({ cardCompany: 'KB국민카드', cardNumber: '', expiryDate: '', cvc: '' });
        loadSubscriptionData();
      } else {
        alert(`[결제수단 등록 실패]\n${data.message}`);
      }
    })
    .catch(err => {
      setIsSubmitting(false);
      alert("결제수단 연동 중 오류가 발생했습니다.");
    });
  };

  // 환불 신청 핸들러
  const handleRequestRefund = (historyId) => {
    if (window.confirm("정말 환불을 신청하시겠습니까?")) {
      fetch(`${baseUrl}/api/subscription/refund`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ paymentId: historyId, brandId: brandId })
      })
      .then(res => res.json())
      .then(data => {
        alert(data.message);
        if (data.success) {
          loadSubscriptionData(); // 내 페이지 데이터 다시 로드
          if (refreshUserStatus) {
            refreshUserStatus(); // 🌟 상위 App.jsx의 전역 상태 갱신
          }
        }
      });
    }
  };

  if (isLoading) {
    return <div style={{ textAlign: 'center', padding: '100px' }}>구독 및 결제 정보를 불러오는 중입니다...</div>;
  }

  return (
    <div style={styles.container}>
      <h2 style={styles.title}>구독 및 결제 상세 관리</h2>

      {/* 1. 현재 구독 플랜 정보 카드 */}
      <div style={styles.sectionCard}>
        <h3 style={styles.sectionTitle}>💳 내 구독 현황</h3>
        {!subInfo || !subInfo.isSubscribed || subInfo.status !== 'ACTIVE' ? (
          <div style={{ textAlign: 'center', padding: '20px 0' }}>
            <p style={{ color: '#64748b', marginBottom: '15px' }}>현재 이용 중인 구독 플랜이 없습니다.</p>
            <button style={styles.primaryButton} onClick={() => onNavigate('subscription')}>
              구독 플랜 둘러보기
            </button>
          </div>
        ) : (
          <div>
            <div style={styles.infoRow}>
              <span>이용 플랜</span>
              <strong style={{ color: '#2563eb', fontSize: '1.1rem' }}>[{subInfo.planName}] 플랜 이용 중 💖</strong>
            </div>
            <div style={styles.infoRow}>
              <span>다음 결제 예정일</span>
              <strong>{subInfo.nextBillingDate}</strong>
            </div>
            <div style={styles.infoRow}>
              <span>다음 결제 예정 금액</span>
              <strong>{subInfo.price?.toLocaleString()}원</strong>
            </div>

            {subInfo.cancelReserved && (
              <div style={styles.warningBox}>
                ⚠️ 현재 구독 해지 신청이 예약된 상태입니다. (다음 결제 전일까지 정상 이용 가능)
              </div>
            )}

            <div style={styles.buttonGroup}>
              <button style={styles.secondaryButton} onClick={() => onNavigate('subscription')}>
                플랜 변경하기
              </button>
              <button 
                style={subInfo.cancelReserved ? styles.restoreButton : styles.dangerButton} 
                onClick={handleCancelToggle}
              >
                {subInfo.cancelReserved ? '해지 신청 취소' : '구독 해지'}
              </button>
            </div>
          </div>
        )}
      </div>

      {/* 2. 자동 결제 수단 정보 카드 */}
      <div style={styles.sectionCard}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '15px' }}>
          <h3 style={{ ...styles.sectionTitle, marginBottom: 0 }}>🔒 등록된 자동 결제 수단</h3>
          <button style={styles.smallOutlineButton} onClick={() => setIsPaymentModalOpen(true)}>
            + 결제 수단 변경/등록
          </button>
        </div>

        {paymentMethod ? (
          <div style={styles.paymentMethodBox}>
            <div>
              <span style={{ fontWeight: 'bold', fontSize: '1.05rem', color: '#1e293b' }}>
                {paymentMethod.provider_name || '신용카드'}
              </span>
              {paymentMethod.card_number && (
                <span style={{ color: '#64748b', marginLeft: '10px', fontSize: '0.95rem' }}>
                  ({paymentMethod.card_number})
                </span>
              )}
            </div>
            <span style={{ fontSize: '0.85rem', color: '#10b981', fontWeight: 'bold', backgroundColor: '#ecfdf5', padding: '4px 8px', borderRadius: '4px' }}>
              ✓ 대표 결제수단
            </span>
          </div>
        ) : (
          <p style={{ color: '#888', fontSize: '0.95rem' }}>등록된 자동 결제 수단이 없습니다.</p>
        )}
      </div>

      {/* 3. 결제 내역 카드 */}
      <div style={styles.sectionCard}>
        <h3 style={styles.sectionTitle}>📄 결제 내역 및 영수증</h3>

        {history && history.length > 0 ? (
          <div style={{ overflowX: 'auto' }}>
            <table style={styles.table}>
              <thead>
                <tr style={styles.thRow}>
                  <th style={styles.th}>결제일자</th>
                  <th style={styles.th}>결제 플랜</th>
                  <th style={styles.th}>결제 금액</th>
                  <th style={styles.th}>결제 수단</th>
                  <th style={styles.th}>관리</th>
                </tr>
              </thead>
              <tbody>
                {history.map((item) => {
                  const paidDate = new Date(item.paid_at);
                  const diffDays = (new Date() - paidDate) / (1000 * 60 * 60 * 24);
                  const isRefundable = item.status !== 'REFUNDED' && diffDays <= 7;

                  return (
                    <tr key={item.history_id} style={styles.tdRow}>
                      <td style={styles.td}>{item.paid_at}</td>
                      <td style={{ ...styles.td, fontWeight: 'bold' }}>{item.plan_name}</td>
                      <td style={styles.td}>{item.amount?.toLocaleString()}원</td>
                      <td style={styles.td}>{item.payment_method || '간편결제'}</td>
                      <td style={{ ...styles.td, display: 'flex', gap: '6px', justifyContent: 'center', alignItems: 'center' }}>
                        <button style={styles.receiptButton} onClick={() => setSelectedReceipt(item)}>
                          영수증 보기
                        </button>

                        {item.status === 'REFUNDED' ? (
                          <span style={{ fontSize: '0.82rem', color: '#ef4444', fontWeight: 'bold', padding: '4px 8px' }}>
                            환불 완료
                          </span>
                        ) : isRefundable ? (
                          <button 
                            style={{ ...styles.receiptButton, backgroundColor: '#fef2f2', color: '#dc2626', borderColor: '#fecaca', fontWeight: 'bold' }}
                            onClick={() => handleRequestRefund(item.history_id)}
                          >
                            환불 신청
                          </button>
                        ) : null}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <p style={{ color: '#888', textAlign: 'center', padding: '20px 0' }}>결제 내역이 존재하지 않습니다.</p>
        )}
      </div>

      {/* 결제 및 환불 영수증 모달 */}
      {selectedReceipt && (
        <div style={styles.modalOverlay}>
          <div style={styles.modalContent}>
            <div style={styles.receiptHeader}>
              <h3 style={{ margin: 0, fontSize: '1.3rem', color: '#0f172a' }}>
                {selectedReceipt.status === 'REFUNDED' ? '🧾 결제 및 환불 영수증' : '🧾 구매 영수증'}
              </h3>
              <p style={{ fontSize: '0.82rem', color: '#64748b', marginTop: '6px' }}>
                거래번호: REC-{selectedReceipt.history_id * 100023}
              </p>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '15px' }}>
              <div style={{ backgroundColor: '#f8fafc', padding: '15px', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
                <h4 style={{ margin: '0 0 10px 0', fontSize: '0.95rem', color: '#1e293b', borderBottom: '1px solid #cbd5e1', paddingBottom: '6px' }}>
                  💳 결제 정보 (승인 완료)
                </h4>
                <div style={styles.infoRow}><span>결제일시</span><strong>{selectedReceipt.paid_at}</strong></div>
                <div style={styles.infoRow}><span>상품명</span><strong>{selectedReceipt.plan_name} 플랜</strong></div>
                <div style={styles.infoRow}><span>결제 수단</span><strong>{selectedReceipt.payment_method || '신용카드'}</strong></div>
                <div style={styles.infoRow}><span>결제 금액</span><strong>{selectedReceipt.amount?.toLocaleString()}원</strong></div>
              </div>

              {selectedReceipt.status === 'REFUNDED' && (
                <div style={{ backgroundColor: '#fef2f2', padding: '15px', borderRadius: '8px', border: '1px solid #fecaca' }}>
                  <h4 style={{ margin: '0 0 10px 0', fontSize: '0.95rem', color: '#dc2626', borderBottom: '1px solid #fca5a5', paddingBottom: '6px' }}>
                    🔄 환불 처리 정보 (승인 취소)
                  </h4>
                  <div style={styles.infoRow}><span>환불일시</span><strong style={{ color: '#dc2626' }}>{selectedReceipt.refunded_at || selectedReceipt.paid_at}</strong></div>
                  <div style={styles.infoRow}><span>처리 상태</span><strong style={{ color: '#dc2626' }}>환불 완료 (승인 취소)</strong></div>
                  <div style={styles.infoRow}><span>환불 수단</span><strong>원결제 수단 취소</strong></div>
                  <div style={styles.infoRow}><span>환불 금액</span><strong style={{ color: '#dc2626' }}>-{selectedReceipt.amount?.toLocaleString()}원</strong></div>
                </div>
              )}
            </div>

            <div style={styles.modalButtons}>
              <button style={styles.primaryButton} onClick={() => window.print()}>인쇄 / PDF 저장</button>
              <button style={styles.closeBtn} onClick={() => setSelectedReceipt(null)}>닫기</button>
            </div>
          </div>
        </div>
      )}

      {/* 카드 등록 모달 */}
      {isPaymentModalOpen && (
        <div style={styles.modalOverlay}>
          <div style={styles.modalContent}>
            <div style={styles.receiptHeader}>
              <h3 style={{ margin: 0, fontSize: '1.3rem' }}>💳 결제 수단 등록 / 변경</h3>
              <p style={{ fontSize: '0.85rem', color: '#666', marginTop: '5px' }}>
                카드 유효성 확인을 위해 <strong>100원 결제 승인 후 즉시 취소</strong>됩니다.
              </p>
            </div>

            <form onSubmit={handleRegisterCard} style={{ display: 'flex', flexDirection: 'column', gap: '15px' }}>
              <div>
                <label style={styles.label}>카드사 선택</label>
                <select 
                  style={styles.input} 
                  value={cardForm.cardCompany}
                  onChange={(e) => setCardForm({ ...cardForm, cardCompany: e.target.value })}
                >
                  <option value="KB국민카드">KB국민카드</option>
                  <option value="신한카드">신한카드</option>
                  <option value="삼성카드">삼성카드</option>
                  <option value="현대카드">현대카드</option>
                  <option value="롯데카드">롯데카드</option>
                  <option value="BC카드">BC카드</option>
                  <option value="NH농협카드">NH농협카드</option>
                </select>
              </div>

              <div>
                <label style={styles.label}>카드 번호</label>
                <input 
                  type="text" 
                  placeholder="1234-5678-0000-0000"
                  value={cardForm.cardNumber}
                  onChange={(e) => setCardForm({ ...cardForm, cardNumber: e.target.value })}
                  style={styles.input}
                  required
                />
              </div>

              <div style={{ display: 'flex', gap: '10px' }}>
                <div style={{ flex: 1 }}>
                  <label style={styles.label}>유효기간 (MM/YY)</label>
                  <input 
                    type="text" 
                    placeholder="MM/YY" 
                    value={cardForm.expiryDate}
                    onChange={(e) => setCardForm({ ...cardForm, expiryDate: e.target.value })}
                    style={styles.input}
                    required
                  />
                </div>
                <div style={{ flex: 1 }}>
                  <label style={styles.label}>CVC (3자리)</label>
                  <input 
                    type="password" 
                    maxLength="3"
                    placeholder="***"
                    value={cardForm.cvc}
                    onChange={(e) => setCardForm({ ...cardForm, cvc: e.target.value })}
                    style={styles.input}
                    required
                  />
                </div>
              </div>

              <div style={styles.modalButtons}>
                <button type="button" style={styles.closeBtn} onClick={() => setIsPaymentModalOpen(false)}>
                  취소
                </button>
                <button type="submit" style={styles.primaryButton} disabled={isSubmitting}>
                  {isSubmitting ? '100원 확인 중...' : '카드 검증 및 등록'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

const styles = {
  container: { padding: '40px 20px', maxWidth: '720px', width: '100%', margin: '0 auto', fontFamily: 'sans-serif', backgroundColor: '#ffffff', minHeight: '100vh', boxSizing: 'border-box' },
  title: { textAlign: 'center', marginBottom: '35px', color: '#0f172a', fontSize: '1.8rem', fontWeight: 'bold' },
  sectionCard: { backgroundColor: '#fff', borderRadius: '12px', padding: '25px', marginBottom: '25px', border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.05)' },
  sectionTitle: { fontSize: '1.2rem', fontWeight: 'bold', color: '#1e293b', marginBottom: '20px', borderBottom: '2px solid #f1f5f9', paddingBottom: '10px' },
  infoRow: { display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid #f8fafc', color: '#475569', fontSize: '0.92rem' },
  warningBox: { backgroundColor: '#fef2f2', border: '1px solid #fecaca', padding: '12px', borderRadius: '8px', margin: '15px 0', color: '#dc2626', fontSize: '0.9rem', fontWeight: '500' },
  buttonGroup: { display: 'flex', gap: '12px', justifyContent: 'flex-end', marginTop: '20px' },
  primaryButton: { padding: '10px 20px', backgroundColor: '#0f172a', color: 'white', border: 'none', borderRadius: '6px', cursor: 'pointer', fontWeight: 'bold' },
  secondaryButton: { padding: '10px 18px', backgroundColor: '#3b82f6', color: 'white', border: 'none', borderRadius: '6px', cursor: 'pointer', fontWeight: 'bold' },
  dangerButton: { padding: '10px 18px', backgroundColor: '#fff', color: '#ef4444', border: '1px solid #ef4444', borderRadius: '6px', cursor: 'pointer', fontWeight: 'bold' },
  restoreButton: { padding: '10px 18px', backgroundColor: '#10b981', color: 'white', border: 'none', borderRadius: '6px', cursor: 'pointer', fontWeight: 'bold' },
  paymentMethodBox: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', backgroundColor: '#f8fafc', padding: '15px 20px', borderRadius: '8px', border: '1px solid #e2e8f0' },
  smallOutlineButton: { padding: '6px 12px', backgroundColor: '#fff', border: '1px solid #cbd5e1', color: '#475569', borderRadius: '6px', cursor: 'pointer', fontSize: '0.85rem', fontWeight: 'bold' },
  table: { width: '100%', borderCollapse: 'collapse', textAlign: 'center', fontSize: '0.95rem' },
  thRow: { backgroundColor: '#f1f5f9', color: '#334155' },
  th: { padding: '12px', borderBottom: '2px solid #e2e8f0' },
  tdRow: { borderBottom: '1px solid #f1f5f9' },
  td: { padding: '12px', color: '#475569' },
  receiptButton: { padding: '5px 10px', backgroundColor: '#f1f5f9', border: '1px solid #cbd5e1', borderRadius: '4px', cursor: 'pointer', fontSize: '0.85rem', color: '#1e293b' },
  modalOverlay: { position: 'fixed', top: 0, left: 0, width: '100vw', height: '100vh', backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 },
  modalContent: { backgroundColor: '#fff', width: '480px', padding: '30px', borderRadius: '12px', boxShadow: '0 10px 25px rgba(0,0,0,0.2)' },
  receiptHeader: { textAlign: 'center', marginBottom: '20px', borderBottom: '2px solid #1e293b', paddingBottom: '15px' },
  modalButtons: { display: 'flex', gap: '10px', marginTop: '20px', justifyContent: 'flex-end' },
  closeBtn: { padding: '10px 20px', backgroundColor: '#e2e8f0', color: '#334155', border: 'none', borderRadius: '6px', cursor: 'pointer', fontWeight: 'bold' },
  label: { display: 'block', fontSize: '0.85rem', fontWeight: 'bold', color: '#334155', marginBottom: '6px' },
  input: { width: '100%', padding: '10px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '0.95rem', boxSizing: 'border-box' }
};

export default MySubscriptionPage;