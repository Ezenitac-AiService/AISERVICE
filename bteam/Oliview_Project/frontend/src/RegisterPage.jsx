import React, { useState } from 'react';

function RegisterPage({ onNavigate, apiBaseUrl }) {
  const [step, setStep] = useState(1);

  const [agreeAll, setAgreeAll] = useState(false);
  const [agreeTerms, setAgreeTerms] = useState(false);
  const [agreePrivacy, setAgreePrivacy] = useState(false);
  const [agreePayment, setAgreePayment] = useState(false);

  const [termsModalType, setTermsModalType] = useState(null);

  const [showBrandSearchModal, setShowBrandSearchModal] = useState(false);
  const [brandSearchKeyword, setBrandSearchKeyword] = useState('');
  const [brandSearchResults, setBrandSearchResults] = useState([]);

  const [brandId, setBrandId] = useState('');
  const [brandPw, setBrandPw] = useState('');
  const [showBrandPw, setShowBrandPw] = useState(false);
  
  const [managers, setManagers] = useState([
    { name: '', email: '', password: '', showPassword: false, authCode: '', isVerified: false, isEmailSent: false },
    { name: '', email: '', password: '', showPassword: false, authCode: '', isVerified: false, isEmailSent: false }
  ]);

  const baseUrl = apiBaseUrl || '';

  const handleAgreeAllChange = (checked) => {
    setAgreeAll(checked);
    setAgreeTerms(checked);
    setAgreePrivacy(checked);
    setAgreePayment(checked);
  };

  const handleSingleAgreeChange = (type, checked) => {
    let t = agreeTerms, p = agreePrivacy, pay = agreePayment;
    if (type === 'terms') t = checked;
    if (type === 'privacy') p = checked;
    if (type === 'payment') pay = checked;

    setAgreeTerms(t);
    setAgreePrivacy(p);
    setAgreePayment(pay);
    setAgreeAll(t && p && pay);
  };

  const handleNextStep = () => {
    if (!agreeTerms || !agreePrivacy || !agreePayment) {
      alert('모든 필수 약관에 동의하셔야 회원가입을 진행할 수 있습니다.');
      return;
    }
    setStep(2);
    window.scrollTo(0, 0);
  };

  const handleSearchBrands = async () => {
    try {
      const res = await fetch(`${baseUrl}/api/search-brands?keyword=${encodeURIComponent(brandSearchKeyword)}`);
      const data = await res.json();
      if (data.success) {
        setBrandSearchResults(data.brands);
      }
    } catch (err) {
      alert("브랜드 조회 중 오류가 발생했습니다.");
    }
  };

  const handleManagerChange = (index, field, value) => {
    let sanitizedValue = value;
    if (field === 'name') {
      sanitizedValue = value.replace(/[^ㄱ-ㅎㅏ-ㅣ가-힣a-zA-Z]/g, '');
    } else if (field === 'password') {
      sanitizedValue = value.replace(/[ㄱ-ㅎㅏ-ㅣ가-힣]/g, '');
    }

    const newManagers = [...managers];
    newManagers[index][field] = sanitizedValue;
    setManagers(newManagers);
  };

  const toggleManagerPassword = (index) => {
    const newManagers = [...managers];
    newManagers[index].showPassword = !newManagers[index].showPassword;
    setManagers(newManagers);
  };

  const sendAuthCode = async (index) => {
    const email = managers[index].email;
    if (!email) return alert('이메일을 입력해주세요.');

    try {
      const checkRes = await fetch(`${baseUrl}/api/check-email`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email })
      });
      const checkData = await checkRes.json();

      if (checkData.isDuplicate) {
        alert('이미 다른 계정에서 사용 중인 이메일입니다.');
        return;
      }

      const res = await fetch(`${baseUrl}/api/send-auth-code`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email })
      });
      const data = await res.json();
      alert(data.message);
      
      if (data.success) {
        const newManagers = [...managers];
        newManagers[index].isEmailSent = true;
        setManagers(newManagers);
      }
    } catch (e) {
      alert('발송 실패');
    }
  };

  const verifyAuthCode = async (index) => {
    const { email, authCode } = managers[index];
    if (!authCode) return alert('인증번호를 입력해주세요.');

    try {
      const res = await fetch(`${baseUrl}/api/verify-auth-code`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, code: authCode })
      });
      const data = await res.json();
      
      if (data.success) {
        alert('이메일 인증이 완료되었습니다.');
        const newManagers = [...managers];
        newManagers[index].isVerified = true;
        setManagers(newManagers);
      } else {
        alert(data.message);
      }
    } catch (e) {
      alert('인증 실패');
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!managers[0].isVerified) {
      alert('첫 번째 담당자의 이메일 인증을 완료해주세요.');
      return;
    }

    try {
      const response = await fetch(`${baseUrl}/api/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ brandId, brandPw, managers })
      });
      
      const result = await response.json();
      if (result.success) {
        alert('회원가입이 완료되었습니다!');
        onNavigate('login');
      } else {
        alert(result.message);
      }
    } catch (error) {
      console.error("회원가입 에러:", error);
    }
  };

  const handleBrandIdChange = (e) => {
    const onlyNumbers = e.target.value.replace(/[^0-9]/g, '');
    setBrandId(onlyNumbers);
  };

  const handleBrandPwChange = (e) => {
    const noKorean = e.target.value.replace(/[ㄱ-ㅎㅏ-ㅣ가-힣]/g, '');
    setBrandPw(noKorean);
  };

  return (
    <div style={styles.container}>
      <h2 style={styles.title}>브랜드 회원가입</h2>

      {step === 1 && (
        <div style={styles.sectionCard}>
          <h3 style={styles.sectionTitle}>STEP 01. 약관 동의</h3>
          
          <div style={styles.agreeAllBox}>
            <label style={styles.agreeAllLabel}>
              <input 
                type="checkbox" 
                checked={agreeAll} 
                onChange={(e) => handleAgreeAllChange(e.target.checked)}
                style={styles.checkbox}
              />
              <span style={{ fontWeight: 'bold', fontSize: '1rem' }}>서비스 이용약관 전체 동의</span>
            </label>
          </div>

          <div style={styles.termsList}>
            <div style={styles.termsItem}>
              <label style={styles.termsLabel}>
                <input 
                  type="checkbox" 
                  checked={agreeTerms} 
                  onChange={(e) => handleSingleAgreeChange('terms', e.target.checked)}
                  style={styles.checkbox}
                />
                <span><strong style={{ color: '#d97706' }}>[필수]</strong> 서비스 이용약관 동의</span>
              </label>
              <button type="button" onClick={() => setTermsModalType('terms')} style={styles.viewBtn}>전문보기</button>
            </div>

            <div style={styles.termsItem}>
              <label style={styles.termsLabel}>
                <input 
                  type="checkbox" 
                  checked={agreePrivacy} 
                  onChange={(e) => handleSingleAgreeChange('privacy', e.target.checked)}
                  style={styles.checkbox}
                />
                <span><strong style={{ color: '#d97706' }}>[필수]</strong> 개인정보 수집 및 이용 동의</span>
              </label>
              <button type="button" onClick={() => setTermsModalType('privacy')} style={styles.viewBtn}>전문보기</button>
            </div>

            <div style={styles.termsItem}>
              <label style={styles.termsLabel}>
                <input 
                  type="checkbox" 
                  checked={agreePayment} 
                  onChange={(e) => handleSingleAgreeChange('payment', e.target.checked)}
                  style={styles.checkbox}
                />
                <span><strong style={{ color: '#d97706' }}>[필수]</strong> 전자상거래 및 정기결제 약관 동의</span>
              </label>
              <button type="button" onClick={() => setTermsModalType('payment')} style={styles.viewBtn}>전문보기</button>
            </div>
          </div>

          <button onClick={handleNextStep} style={{ ...styles.primaryButton, width: '100%', marginTop: '20px' }}>
            다음 (회원정보 입력)
          </button>

          <div style={{ textAlign: 'center', marginTop: '15px' }}>
            <button onClick={() => onNavigate('main')} style={styles.backButton}>메인으로 돌아가기</button>
          </div>
        </div>
      )}

      {step === 2 && (
        <form onSubmit={handleSubmit} style={{ width: '100%' }}>
          <div style={styles.sectionCard}>
            <h3 style={styles.sectionTitle}>🏢 브랜드 정보</h3>
            
            <div style={styles.formGroup}>
              <label style={styles.label}>브랜드 고유 번호</label>
              <div style={styles.passwordWrapper}>
                <input 
                  type="text" 
                  placeholder="숫자만 입력 가능합니다" 
                  value={brandId} 
                  onChange={handleBrandIdChange} 
                  required 
                  style={{ ...styles.input, flex: 1 }}
                />
                <button 
                  type="button" 
                  onClick={() => { setShowBrandSearchModal(true); handleSearchBrands(); }} 
                  style={styles.actionBtn}
                >
                  조회하기
                </button>
              </div>
            </div>
            
            <div style={styles.formGroup}>
              <label style={styles.label}>브랜드 비밀번호</label>
              <div style={styles.passwordWrapper}>
                <input 
                  type={showBrandPw ? "text" : "password"} 
                  placeholder="영문, 숫자, 특수문자 포함" 
                  value={brandPw} 
                  onChange={handleBrandPwChange} 
                  required 
                  style={{ ...styles.input, flex: 1 }}
                />
                <button 
                  type="button" 
                  style={styles.toggleBtn} 
                  onClick={() => setShowBrandPw(!showBrandPw)}
                >
                  {showBrandPw ? "숨기기" : "보기"}
                </button>
              </div>
            </div>
          </div>

          <div style={styles.sectionCard}>
            <h3 style={styles.sectionTitle}>👤 담당자 정보</h3>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '15px' }}>
              {[0, 1].map((index) => (
                <div key={index} style={styles.managerContainer}>
                  <div style={styles.managerTitle}>담당자 {index + 1} {index === 1 && '(선택)'}</div>
                  
                  <div style={styles.formGroup}>
                    <label style={styles.label}>담당자 이름</label>
                    <input 
                      type="text" 
                      placeholder="한글, 영문만 입력 가능합니다" 
                      value={managers[index].name} 
                      onChange={(e) => handleManagerChange(index, 'name', e.target.value)} 
                      required={index === 0}
                      style={styles.input}
                    />
                  </div>
                  
                  <div style={styles.formGroup}>
                    <label style={styles.label}>담당자 비밀번호</label>
                    <div style={styles.passwordWrapper}>
                      <input 
                        type={managers[index].showPassword ? "text" : "password"} 
                        placeholder="영문, 숫자, 특수문자 포함" 
                        value={managers[index].password} 
                        onChange={(e) => handleManagerChange(index, 'password', e.target.value)} 
                        required={index === 0}
                        style={{ ...styles.input, flex: 1 }}
                      />
                      <button 
                        type="button" 
                        style={styles.toggleBtn} 
                        onClick={() => toggleManagerPassword(index)}
                      >
                        {managers[index].showPassword ? "숨기기" : "보기"}
                      </button>
                    </div>
                  </div>
                  
                  <div style={styles.formGroup}>
                    <label style={styles.label}>담당자 이메일</label>
                    <div style={styles.passwordWrapper}>
                      <input 
                        type="email" 
                        placeholder="이메일을 입력하세요" 
                        value={managers[index].email} 
                        onChange={(e) => handleManagerChange(index, 'email', e.target.value)} 
                        readOnly={managers[index].isVerified}
                        style={{ ...styles.input, flex: 1, backgroundColor: managers[index].isVerified ? '#f8fafc' : '#fff' }}
                      />
                      <button 
                        type="button" 
                        onClick={() => sendAuthCode(index)} 
                        disabled={managers[index].isVerified}
                        style={styles.actionBtn}
                      >
                        인증번호 발송
                      </button>
                    </div>
                  </div>

                  {managers[index].isEmailSent && !managers[index].isVerified && (
                    <div style={styles.formGroup}>
                      <label style={styles.label}>인증번호 입력</label>
                      <div style={styles.passwordWrapper}>
                        <input 
                          type="text" 
                          placeholder="메일로 받은 6자리 숫자" 
                          value={managers[index].authCode} 
                          onChange={(e) => handleManagerChange(index, 'authCode', e.target.value)} 
                          style={{ ...styles.input, flex: 1 }}
                        />
                        <button 
                          type="button" 
                          onClick={() => verifyAuthCode(index)} 
                          style={styles.actionBtn}
                        >
                          확인
                        </button>
                      </div>
                    </div>
                  )}
                  
                  {managers[index].isVerified && (
                    <div style={{ color: '#16a34a', fontSize: '0.85rem', fontWeight: 'bold' }}>
                      ✓ 이메일 인증 완료
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>

          <button type="submit" style={{ ...styles.primaryButton, width: '100%' }}>
            회원가입 완료
          </button>

          <div style={{ textAlign: 'center', marginTop: '15px' }}>
            <button type="button" onClick={() => setStep(1)} style={styles.backButton}>
              이전 단계로 (약관 다시보기)
            </button>
          </div>
        </form>
      )}

      {showBrandSearchModal && (
        <div style={styles.modalOverlay}>
          <div style={styles.modalContent}>
            <h3 style={styles.modalTitle}>브랜드 고유번호 조회</h3>
            <div style={{ display: 'flex', gap: '8px', marginBottom: '15px' }}>
              <input 
                type="text" 
                placeholder="브랜드명 입력" 
                value={brandSearchKeyword} 
                onChange={(e) => setBrandSearchKeyword(e.target.value)}
                style={{ ...styles.input, flex: 1 }}
              />
              <button onClick={handleSearchBrands} style={styles.actionBtn}>검색</button>
            </div>
            <div style={styles.modalList}>
              {brandSearchResults.length > 0 ? (
                brandSearchResults.map((b) => (
                  <div 
                    key={b.brand_id} 
                    style={styles.modalListItem}
                    onClick={() => {
                      setBrandId(String(b.brand_id));
                      setShowBrandSearchModal(false);
                    }}
                  >
                    <span style={{ fontWeight: 'bold' }}>{b.brand_name}</span>
                    <span style={{ color: '#2563eb', fontSize: '0.85rem' }}>ID: {b.brand_id}</span>
                  </div>
                ))
              ) : (
                <p style={{ color: '#888', fontSize: '0.9rem', textAlign: 'center', padding: '20px 0' }}>검색 결과가 없습니다.</p>
              )}
            </div>
            <button onClick={() => setShowBrandSearchModal(false)} style={styles.closeBtn}>닫기</button>
          </div>
        </div>
      )}

      {termsModalType && (
        <div style={styles.modalOverlay}>
          <div style={styles.modalContent}>
            <h3 style={styles.modalTitle}>
              {termsModalType === 'terms' && '서비스 이용약관'}
              {termsModalType === 'privacy' && '개인정보 수집 및 이용 동의'}
              {termsModalType === 'payment' && '전자상거래 및 정기결제 약관'}
            </h3>
            
            <div style={styles.modalTextBody}>
              {termsModalType === 'terms' && (
                <p>
                  <strong>제 1 조 (목적)</strong><br />
                  본 약관은 Oliview(이하 "회사")가 제공하는 브랜드 데이터 분석 플랫폼 서비스의 이용조건 및 절차를 규정합니다.<br /><br />
                  <strong>제 2 조 (회원가입 및 계정)</strong><br />
                  1. 회사는 정한 양식에 따라 신청을 진행합니다.<br />
                  2. 올리브영 입점 브랜드 담당자만 이용 가능합니다.
                </p>
              )}

              {termsModalType === 'privacy' && (
                <p>
                  <strong>1. 수집하는 개인정보 항목</strong><br />
                  - 필수항목: 브랜드 고유번호, 담당자 이름, 이메일, 비밀번호<br /><br />
                  <strong>2. 이용목적</strong><br />
                  - 본인 확인 및 리포트/알림 제공<br /><br />
                  <strong>3. 보유기간</strong><br />
                  - 탈퇴 신청 시 30일 유예 후 파기[cite: 20]
                </p>
              )}

              {termsModalType === 'payment' && (
                <p>
                  <strong>1. 구독 결제 및 자동 갱신</strong><br />
                  - 매월 지정 결제일에 자동 청구됩니다.<br /><br />
                  <strong>2. 해지 및 환불 정책</strong><br />
                  - 결제 후 미이용 시 7일 이내 환불 가능합니다.
                </p>
              )}
            </div>

            <button onClick={() => setTermsModalType(null)} style={styles.closeBtn}>
              확인 및 닫기
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

const styles = {
  container: { padding: '40px 20px', maxWidth: '720px', width: '100%', margin: '0 auto', fontFamily: 'sans-serif', backgroundColor: '#ffffff', minHeight: '100vh', boxSizing: 'border-box' },
  title: { textAlign: 'center', marginBottom: '35px', color: '#0f172a', fontSize: '1.8rem', fontWeight: 'bold' },
  sectionCard: { backgroundColor: '#fff', borderRadius: '12px', padding: '28px', marginBottom: '25px', border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.05)' },
  sectionTitle: { fontSize: '1.2rem', fontWeight: 'bold', color: '#1e293b', marginBottom: '20px', borderBottom: '2px solid #f1f5f9', paddingBottom: '10px' },
  agreeAllBox: { padding: '16px', backgroundColor: '#f8fafc', border: '1px solid #cbd5e1', borderRadius: '8px', marginBottom: '15px' },
  agreeAllLabel: { display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer' },
  termsList: { display: 'flex', flexDirection: 'column', gap: '12px' },
  termsItem: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 4px', borderBottom: '1px solid #f1f5f9' },
  termsLabel: { display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.9rem', cursor: 'pointer', color: '#334155' },
  checkbox: { width: '18px', height: '18px', cursor: 'pointer' },
  viewBtn: { background: 'none', border: 'none', color: '#64748b', fontSize: '0.82rem', textDecoration: 'underline', cursor: 'pointer' },
  formGroup: { display: 'flex', flexDirection: 'column', gap: '8px', textAlign: 'left', marginBottom: '16px' },
  label: { fontSize: '0.88rem', fontWeight: 'bold', color: '#333' },
  input: { padding: '12px 14px', fontSize: '0.95rem', border: '1px solid #cbd5e1', borderRadius: '6px', outline: 'none', backgroundColor: '#fff', width: '100%', boxSizing: 'border-box' },
  passwordWrapper: { display: 'flex', gap: '8px', alignItems: 'center' },
  toggleBtn: { padding: '12px 14px', backgroundColor: '#f8fafc', border: '1px solid #cbd5e1', borderRadius: '6px', cursor: 'pointer', fontSize: '0.85rem', fontWeight: '600', color: '#475569', whiteSpace: 'nowrap' },
  actionBtn: { padding: '12px 16px', backgroundColor: '#0f172a', color: '#fff', border: 'none', borderRadius: '6px', cursor: 'pointer', fontSize: '0.85rem', fontWeight: 'bold', whiteSpace: 'nowrap' },
  managerContainer: { display: 'flex', flexDirection: 'column', gap: '12px', padding: '16px', backgroundColor: '#f8fafc', borderRadius: '8px', border: '1px solid #e2e8f0' },
  managerTitle: { fontSize: '0.95rem', fontWeight: 'bold', color: '#0f172a' },
  primaryButton: { padding: '14px', backgroundColor: '#0f172a', color: '#fff', fontSize: '1rem', fontWeight: 'bold', border: 'none', borderRadius: '6px', cursor: 'pointer' },
  backButton: { background: 'none', border: 'none', color: '#64748b', cursor: 'pointer', fontSize: '0.9rem', textDecoration: 'underline' },
  
  modalOverlay: { position: 'fixed', top: 0, left: 0, width: '100vw', height: '100vh', backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', justifyContent: 'center', alignItems: 'center', zIndex: 1000 },
  modalContent: { width: '90%', maxWidth: '440px', backgroundColor: '#fff', padding: '24px', borderRadius: '12px', boxShadow: '0 4px 20px rgba(0,0,0,0.15)', textAlign: 'left' },
  modalTitle: { fontSize: '1.15rem', fontWeight: 'bold', marginBottom: '15px', color: '#111' },
  modalList: { maxHeight: '200px', overflowY: 'auto', border: '1px solid #e2e8f0', borderRadius: '6px', padding: '8px' },
  modalListItem: { display: 'flex', justifyContent: 'space-between', padding: '10px', borderBottom: '1px solid #f1f5f9', cursor: 'pointer' },
  modalTextBody: { maxHeight: '250px', overflowY: 'auto', backgroundColor: '#f8fafc', padding: '14px', borderRadius: '8px', fontSize: '0.85rem', color: '#334155', lineHeight: '1.6', border: '1px solid #e2e8f0' },
  closeBtn: { width: '100%', padding: '12px', backgroundColor: '#e2e8f0', color: '#334155', border: 'none', borderRadius: '6px', cursor: 'pointer', fontWeight: 'bold', marginTop: '15px' }
};

export default RegisterPage;