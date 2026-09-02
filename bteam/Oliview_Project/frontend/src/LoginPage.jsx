import React, { useState } from 'react';

function LoginPage({ onNavigate, setIsLoggedIn, setUser, apiBaseUrl }) {
  const [brandId, setBrandId] = useState('');
  const [email, setEmail] = useState(''); 
  const [managerPw, setManagerPw] = useState('');
  const [showPassword, setShowPassword] = useState(false);

  const [modalType, setModalType] = useState(null);
  const [brandSearchKeyword, setBrandSearchKeyword] = useState('');
  const [brandSearchResults, setBrandSearchResults] = useState([]);

  const [findBrandId, setFindBrandId] = useState('');
  const [findName, setFindName] = useState('');
  const [foundEmailResult, setFoundEmailResult] = useState('');

  const [resetBrandId, setResetBrandId] = useState('');
  const [resetEmail, setResetEmail] = useState('');

  const baseUrl = apiBaseUrl || '';

  const handleBrandIdChange = (e) => {
    const onlyNumbers = e.target.value.replace(/[^0-9]/g, '');
    setBrandId(onlyNumbers);
  };

  const handleManagerPwChange = (e) => {
    const noKorean = e.target.value.replace(/[ㄱ-ㅎㅏ-ㅣ가-힣]/g, '');
    setManagerPw(noKorean);
  };

  const handleLogin = async (e) => {
    e.preventDefault();
    try {
      const response = await fetch(`${baseUrl}/api/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ brandId, email, managerPw })
      });
      
      const result = await response.json();

      if (result.isWithdrawing) {
        const confirmCancel = window.confirm(result.message);
        if (confirmCancel) {
          const cancelRes = await fetch(`${baseUrl}/api/cancel-withdrawal`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ brandId, email, managerPw })
          });
          const cancelData = await cancelRes.json();
          alert(cancelData.message);
          if (cancelData.success) {
            window.location.reload();
          }
        }
        return;
      }

      if (result.success) {
        alert(`${result.managerName || result.manager_name}님 환영합니다!`);
        if (setIsLoggedIn) setIsLoggedIn(true);
        
        const userData = {
          brandId: result.brandId,
          brandName: result.brandName,
          managerName: result.managerName
        };
      
        if (setUser) setUser(userData);
      
        // 🌟 localStorage -> sessionStorage로 변경
        sessionStorage.setItem('oliview_user', JSON.stringify(userData));
        sessionStorage.setItem('oliview_isLoggedIn', 'true');
      
        onNavigate('main');
      } else {
        alert(result.message);
      }
    } catch (error) {
      console.error("로그인 에러:", error);
      alert("서버와 연결할 수 없습니다.");
    }
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

  const handleFindEmail = async () => {
    try {
      const res = await fetch(`${baseUrl}/api/find-email`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ brandId: findBrandId, name: findName })
      });
      const data = await res.json();
      if (data.success) {
        setFoundEmailResult(data.maskedEmail);
      } else {
        alert(data.message);
      }
    } catch (err) {
      alert("이메일 찾기 중 오류가 발생했습니다.");
    }
  };

  const handleResetPassword = async () => {
    try {
      const res = await fetch(`${baseUrl}/api/reset-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ brandId: resetBrandId, email: resetEmail })
      });
      const data = await res.json();
      alert(data.message);
      if (data.success) {
        setModalType(null);
      }
    } catch (err) {
      alert("비밀번호 재설정 중 오류가 발생했습니다.");
    }
  };

  return (
    <div style={styles.container}>
      <h2 style={styles.title}>브랜드 로그인</h2>

      <div style={styles.sectionCard}>
        <h3 style={styles.sectionTitle}>🔒 로그인 정보 입력</h3>
        
        <form onSubmit={handleLogin} style={styles.form}>
          <div style={styles.formGroup}>
            <label style={styles.label}>브랜드 고유 번호</label>
            <div style={{ display: 'flex', gap: '8px' }}>
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
                onClick={() => { setModalType('brandSearch'); handleSearchBrands(); }} 
                style={styles.actionBtn}
              >
                조회하기
              </button>
            </div>
          </div>

          <div style={styles.formGroup}>
            <label style={styles.label}>담당자 이메일</label>
            <input 
              type="email" 
              placeholder="가입 시 인증한 이메일을 입력하세요" 
              value={email} 
              onChange={(e) => setEmail(e.target.value)} 
              required 
              style={styles.input}
            />
          </div>

          <div style={styles.formGroup}>
            <label style={styles.label}>담당자 비밀번호</label>
            <div style={styles.passwordWrapper}>
              <input 
                type={showPassword ? "text" : "password"} 
                placeholder="영문, 숫자, 특수문자 포함" 
                value={managerPw} 
                onChange={handleManagerPwChange} 
                required 
                style={{ ...styles.input, flex: 1 }}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                style={styles.toggleBtn}
              >
                {showPassword ? "숨김" : "보기"}
              </button>
            </div>
          </div>

          <button type="submit" style={styles.primaryButton}>
            로그인 하기
          </button>
        </form>

        <div style={styles.accountLinks}>
          <button type="button" onClick={() => { setModalType('findEmail'); setFoundEmailResult(''); }} style={styles.linkBtn}>
            담당자 이메일 찾기
          </button>
          <span style={{ color: '#ccc' }}>|</span>
          <button type="button" onClick={() => setModalType('resetPw')} style={styles.linkBtn}>
            비밀번호 재설정
          </button>
        </div>

        <div style={styles.registerPrompt}>
          <span style={{ color: '#666', fontSize: '0.9rem' }}>회원이 아니신가요? </span>
          <button onClick={() => onNavigate('register')} style={styles.registerBtn}>
            회원가입 하러 가기
          </button>
        </div>
      </div>

      {modalType && (
        <div style={styles.modalOverlay}>
          <div style={styles.modalContent}>
            {modalType === 'brandSearch' && (
              <>
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
                          setModalType(null);
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
              </>
            )}

            {modalType === 'findEmail' && (
              <>
                <h3 style={styles.modalTitle}>담당자 이메일 찾기</h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginBottom: '15px' }}>
                  <input 
                    type="text" 
                    placeholder="브랜드 고유번호" 
                    value={findBrandId} 
                    onChange={(e) => setFindBrandId(e.target.value)}
                    style={styles.input}
                  />
                  <input 
                    type="text" 
                    placeholder="담당자 이름" 
                    value={findName} 
                    onChange={(e) => setFindName(e.target.value)}
                    style={styles.input}
                  />
                  <button onClick={handleFindEmail} style={styles.actionBtn}>이메일 조회</button>
                </div>
                {foundEmailResult && (
                  <div style={{ padding: '12px', backgroundColor: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '6px', textAlign: 'center', fontSize: '0.95rem' }}>
                    등록된 이메일: <strong>{foundEmailResult}</strong>
                  </div>
                )}
              </>
            )}

            {modalType === 'resetPw' && (
              <>
                <h3 style={styles.modalTitle}>비밀번호 재설정</h3>
                <p style={{ fontSize: '0.85rem', color: '#666', marginBottom: '15px' }}>가입 시 등록한 정보로 임시 비밀번호가 발송됩니다.</p>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginBottom: '15px' }}>
                  <input 
                    type="text" 
                    placeholder="브랜드 고유번호" 
                    value={resetBrandId} 
                    onChange={(e) => setResetBrandId(e.target.value)}
                    style={styles.input}
                  />
                  <input 
                    type="email" 
                    placeholder="담당자 이메일" 
                    value={resetEmail} 
                    onChange={(e) => setResetEmail(e.target.value)}
                    style={styles.input}
                  />
                  <button onClick={handleResetPassword} style={styles.actionBtn}>임시 비밀번호 발송</button>
                </div>
              </>
            )}

            <button onClick={() => setModalType(null)} style={styles.closeBtn}>닫기</button>
          </div>
        </div>
      )}
    </div>
  );
}

const styles = {
  container: { padding: '40px 20px', maxWidth: '520px', width: '100%', margin: '0 auto', fontFamily: 'sans-serif', backgroundColor: '#ffffff', minHeight: '100vh', boxSizing: 'border-box' },
  title: { textAlign: 'center', marginBottom: '35px', color: '#0f172a', fontSize: '1.8rem', fontWeight: 'bold' },
  sectionCard: { backgroundColor: '#fff', borderRadius: '12px', padding: '32px 28px', marginBottom: '25px', border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.05)' },
  sectionTitle: { fontSize: '1.2rem', fontWeight: 'bold', color: '#1e293b', marginBottom: '24px', borderBottom: '2px solid #f1f5f9', paddingBottom: '10px' },
  form: { display: 'flex', flexDirection: 'column', gap: '18px' },
  formGroup: { display: 'flex', flexDirection: 'column', gap: '8px', textAlign: 'left' },
  label: { fontSize: '0.88rem', fontWeight: 'bold', color: '#333' },
  input: { padding: '12px 14px', fontSize: '0.95rem', border: '1px solid #cbd5e1', borderRadius: '6px', outline: 'none', backgroundColor: '#fff', width: '100%', boxSizing: 'border-box' },
  passwordWrapper: { display: 'flex', gap: '8px', alignItems: 'center' },
  toggleBtn: { padding: '12px 14px', backgroundColor: '#f8fafc', border: '1px solid #cbd5e1', borderRadius: '6px', cursor: 'pointer', fontSize: '0.85rem', fontWeight: '600', color: '#475569', whiteSpace: 'nowrap' },
  actionBtn: { padding: '12px 16px', backgroundColor: '#0f172a', color: '#fff', border: 'none', borderRadius: '6px', cursor: 'pointer', fontSize: '0.85rem', fontWeight: 'bold', whiteSpace: 'nowrap' },
  primaryButton: { marginTop: '10px', padding: '14px', backgroundColor: '#0f172a', color: '#fff', fontSize: '1rem', fontWeight: 'bold', border: 'none', borderRadius: '6px', cursor: 'pointer' },
  accountLinks: { display: 'flex', justifyContent: 'center', gap: '12px', marginTop: '20px', fontSize: '0.85rem' },
  linkBtn: { background: 'none', border: 'none', color: '#64748b', cursor: 'pointer', fontSize: '0.85rem', textDecoration: 'underline' },
  registerPrompt: { display: 'flex', alignItems: 'center', justifyContent: 'center', marginTop: '25px', gap: '8px' },
  registerBtn: { padding: '6px 14px', backgroundColor: '#f1f5f9', color: '#0f172a', border: '1px solid #cbd5e1', borderRadius: '20px', cursor: 'pointer', fontSize: '0.85rem', fontWeight: 'bold' },
  
  modalOverlay: { position: 'fixed', top: 0, left: 0, width: '100vw', height: '100vh', backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', justifyContent: 'center', alignItems: 'center', zIndex: 1000 },
  modalContent: { width: '90%', maxWidth: '400px', backgroundColor: '#fff', padding: '24px', borderRadius: '12px', boxShadow: '0 4px 20px rgba(0,0,0,0.15)', textAlign: 'left' },
  modalTitle: { fontSize: '1.2rem', fontWeight: 'bold', marginBottom: '15px', color: '#111' },
  modalList: { maxHeight: '200px', overflowY: 'auto', border: '1px solid #e2e8f0', borderRadius: '6px', padding: '8px' },
  modalListItem: { display: 'flex', justifyContent: 'space-between', padding: '10px', borderBottom: '1px solid #f1f5f9', cursor: 'pointer' },
  closeBtn: { width: '100%', padding: '10px', backgroundColor: '#e2e8f0', border: 'none', borderRadius: '6px', cursor: 'pointer', color: '#334155', fontWeight: 'bold', marginTop: '12px' }
};

export default LoginPage;